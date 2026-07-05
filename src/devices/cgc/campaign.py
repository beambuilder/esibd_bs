"""
Switch-campaign safety tooling (P6.8, [[cgc-sw]]).

CGC limits (vendor email, recorded in notebook 023): per-switch-channel
dissipation < 100 W (pair <= 200 W); at 350 V the output current must
stay <= 300 mA. The operating recipe is non-negotiable:

    1. ramp the PSU voltage at 1 kHz switching frequency up to the
       target (<= 350 V),
    2. THEN ramp the switching frequency at full voltage.

``PSUWatchdog`` is the soft watchdog on PSU readback the campaign
notebook (025) polls between every step: breach -> ERROR event + 10 %
setpoint step-down; a second consecutive breach on the same output ->
both outputs of that supply disabled (abort). ``ramp_voltage_at_1khz()``
and ``ramp_frequency()`` encode the recipe order and stop at the first
breach.

Everything here talks only to the curated lab-layer methods (mA units),
so the whole module runs in test mode against simulated devices — the
P6.8 dry-run gate.
"""
import time

#: CGC per-switch-channel limits ([[cgc-sw]], email via notebook 023).
I_LIMIT_MA = 300.0
P_LIMIT_W = 100.0

#: The safe frequency for voltage ramps (CGC recipe).
RAMP_FREQ_KHZ = 1.0

#: Absolute voltage ceiling of the recipe.
V_MAX = 350.0


class WatchdogBreach(RuntimeError):
    """A PSU readback crossed a campaign limit."""


class PSUWatchdog:
    """
    Soft watchdog on PSU V/I readback.

    Args:
        psus: PSU instances to poll (each = one physical supply with the
            outputs PSU_POS/PSU_NEG feeding one switch pair).
        i_limit_ma: Current limit per output in mA (default 300).
        p_limit_w: Dissipation limit per output in W (default 100;
            P = V_out * I_out, the switch-channel load).
        on_breach: Optional callable ``(psu, psu_num, reading, consecutive)``
            replacing the default action. The default steps the output's
            voltage setpoint down 10 % and, on the second consecutive
            breach of the same output, disables both outputs of that
            supply.

    ``check()`` polls every output once and returns the list of breach
    dicts (empty = all clear). The campaign helpers call it between
    steps; the notebook also calls it from its monitor loop.
    """

    def __init__(self, psus, i_limit_ma=I_LIMIT_MA, p_limit_w=P_LIMIT_W,
                 on_breach=None):
        self.psus = list(psus)
        self.i_limit_ma = float(i_limit_ma)
        self.p_limit_w = float(p_limit_w)
        self.on_breach = on_breach
        # Consecutive-breach counter per (device_id, psu_num).
        self._consecutive = {}

    def check(self):
        """Poll every output once; act on and return any breaches."""
        breaches = []
        for psu in self.psus:
            for psu_num in (psu.PSU_POS, psu.PSU_NEG):
                reading = self._read(psu, psu_num)
                if reading is None:
                    continue
                key = (psu.device_id, psu_num)
                if reading["over_i"] or reading["over_p"]:
                    self._consecutive[key] = self._consecutive.get(key, 0) + 1
                    reading["consecutive"] = self._consecutive[key]
                    self._act(psu, psu_num, reading)
                    breaches.append(reading)
                else:
                    self._consecutive[key] = 0
        return breaches

    def _read(self, psu, psu_num):
        status, voltage, current_a, _ = psu.get_psu_data(psu_num)
        if status != psu.NO_ERR:
            psu.log_event(
                "warning",
                f"watchdog: get_psu_data({psu_num}) returned {status}",
            )
            return None
        current_ma = current_a * 1000.0
        power_w = voltage * current_a
        return {
            "device_id": psu.device_id,
            "psu_num": psu_num,
            "voltage_v": voltage,
            "current_ma": current_ma,
            "power_w": power_w,
            "over_i": current_ma > self.i_limit_ma,
            "over_p": power_w > self.p_limit_w,
        }

    def _act(self, psu, psu_num, reading):
        psu.log_event(
            "error",
            f"WATCHDOG BREACH output {psu_num}: "
            f"{reading['current_ma']:.1f} mA / {reading['power_w']:.1f} W "
            f"(limits {self.i_limit_ma:.0f} mA / {self.p_limit_w:.0f} W), "
            f"consecutive={reading['consecutive']}",
        )
        if self.on_breach is not None:
            self.on_breach(psu, psu_num, reading, reading["consecutive"])
            return
        if reading["consecutive"] >= 2:
            psu.log_event(
                "error",
                "watchdog: second consecutive breach - disabling both outputs",
            )
            psu.set_psu_enable(False, False)
            return
        status, v_set, _ = psu.get_psu_set_output_voltage(psu_num)
        if status == psu.NO_ERR and v_set > 0:
            new_target = round(v_set * 0.9, 3)
            psu.log_event(
                "warning",
                f"watchdog: stepping output {psu_num} down "
                f"{v_set:.1f} V -> {new_target:.1f} V",
            )
            psu.set_psu_output_voltage(psu_num, new_target)

    def reset(self):
        """Forget consecutive-breach history (new measurement point)."""
        self._consecutive.clear()


def _set_switch_frequency(switch, frequency_khz, oscillator=None):
    """Family dispatch: SW takes (khz), SWHR takes (oscillator, khz)."""
    if getattr(switch, "FAMILY", "") == "SWHR":
        return switch.set_frequency_khz(
            0 if oscillator is None else oscillator, frequency_khz
        )
    return switch.set_frequency_khz(frequency_khz)


def ramp_voltage_at_1khz(switch, psu, psu_num, target_v, step_v=10.0,
                         dwell_s=1.0, watchdog=None, oscillator=None,
                         sleep=time.sleep):
    """
    Recipe step 1: ramp one PSU output to ``target_v`` while the switch
    runs at 1 kHz.

    Sets the switch to 1 kHz first, then raises the voltage setpoint in
    ``step_v`` increments, waiting ``dwell_s`` and polling the watchdog
    after every step. Raises ``WatchdogBreach`` (with the ramp already
    halted by the watchdog's own action) on a breach, ``ValueError`` for
    a target above 350 V. Returns the final setpoint.
    """
    if target_v > V_MAX:
        raise ValueError(
            f"target {target_v} V exceeds the CGC ceiling of {V_MAX:.0f} V"
        )
    if target_v < 0:
        raise ValueError("negative targets are not part of the recipe")
    status = _set_switch_frequency(switch, RAMP_FREQ_KHZ, oscillator)
    if status != switch.NO_ERR:
        raise WatchdogBreach(
            f"could not set the {RAMP_FREQ_KHZ:.0f} kHz ramp frequency "
            f"(status {status}) - refusing to ramp voltage"
        )
    status, v_now, _ = psu.get_psu_set_output_voltage(psu_num)
    if status != psu.NO_ERR:
        v_now = 0.0
    while v_now < target_v:
        v_now = min(v_now + step_v, target_v)
        psu.set_psu_output_voltage(psu_num, round(v_now, 3))
        sleep(dwell_s)
        if watchdog is not None and watchdog.check():
            raise WatchdogBreach(
                f"voltage ramp stopped at {v_now:.1f} V (watchdog breach)"
            )
    return v_now


def ramp_frequency(switch, target_khz, steps=None, dwell_s=1.0,
                   watchdog=None, oscillator=None, sleep=time.sleep):
    """
    Recipe step 2: ramp the switching frequency at full voltage.

    Doubles the frequency from 1 kHz until ``target_khz`` (or walks the
    explicit ``steps`` list, in kHz), waiting ``dwell_s`` and polling the
    watchdog after every step — current draw grows with frequency, so
    this is where the envelope gets mapped. Raises ``WatchdogBreach`` on
    a breach. Returns the final frequency in kHz.
    """
    if steps is None:
        steps = []
        f = RAMP_FREQ_KHZ
        while f < target_khz:
            f = min(f * 2.0, target_khz)
            steps.append(f)
        if not steps:
            steps = [target_khz]
    f_now = RAMP_FREQ_KHZ
    for f in steps:
        status = _set_switch_frequency(switch, f, oscillator)
        if status != switch.NO_ERR:
            raise WatchdogBreach(
                f"set_frequency_khz({f}) returned status {status}"
            )
        f_now = f
        sleep(dwell_s)
        if watchdog is not None and watchdog.check():
            raise WatchdogBreach(
                f"frequency ramp stopped at {f_now:g} kHz (watchdog breach)"
            )
    return f_now
