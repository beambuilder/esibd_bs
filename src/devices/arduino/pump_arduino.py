"""
Pump-locker Arduino controller.

Reads temperature, fan PWM, and two water-flow-rate sensors from the
PumpLocker Arduino via serial CSV:

    ``18.69,35,0.00,0.00``

Every 20th line the firmware prints a header — ``parse_data()`` simply
returns None for non-numeric lines, so no separate filtering is needed.
"""

from typing import Any, Dict, Optional

from .arduino import Arduino


class PumpArduino(Arduino):
    """
    Arduino controller for the pump-locker cabinet.

    CSV format (500 ms interval):
        Temperature[degC], Fan_PWR[%], Flow1[L/min], Flow2[L/min]

    Example:
        pump = PumpArduino("pump_01", port="COM3")
        pump.connect()
        pump.start_housekeeping(interval=1.0)
    """

    # ------------------------------------------------------------------
    #  Parsing
    # ------------------------------------------------------------------

    def parse_data(self, data_line: str) -> Optional[Dict[str, Any]]:
        """
        Parse a pump-locker CSV line.

        Expected format: ``18.69,35,0.00,0.00``

        Returns:
            dict with keys *temperature*, *fan_power*, *flow_rate_1*,
            *flow_rate_2*, *raw_data*  — or None on failure.
        """
        try:
            parts = data_line.split(",")
            if len(parts) != 4:
                return None

            temperature = float(parts[0].strip())
            fan_power = int(parts[1].strip())
            flow_rate_1 = float(parts[2].strip())
            flow_rate_2 = float(parts[3].strip())

            return {
                "temperature": temperature,
                "fan_power": fan_power,
                "flow_rate_1": flow_rate_1,
                "flow_rate_2": flow_rate_2,
                "raw_data": data_line,
            }
        except (ValueError, IndexError):
            return None

    # ------------------------------------------------------------------
    #  Simulation
    # ------------------------------------------------------------------

    def _sim_data(self) -> Dict[str, Any]:
        """Plausible pump-locker values for test mode."""
        return {
            "temperature": self._sim_uniform(18.0, 22.0),
            "fan_power": int(self._sim_uniform(25, 45, 0)),
            "flow_rate_1": self._sim_uniform(3.0, 4.0),
            "flow_rate_2": self._sim_uniform(3.0, 4.0),
            "raw_data": "simulated",
        }

    # ------------------------------------------------------------------
    #  Housekeeping
    # ------------------------------------------------------------------

    def hk_monitor(self) -> None:
        """Read and report pump-locker sensor data."""
        try:
            rtn = self.read_arduino_data()

            if rtn is not None:
                self.log_sample("Temp", rtn["temperature"], "degC", fmt=".2f")
                self.log_sample("Fan_PWR", rtn["fan_power"], "%")
                self.log_sample("Flow1", rtn["flow_rate_1"], "L/min", fmt=".2f")
                self.log_sample("Flow2", rtn["flow_rate_2"], "L/min", fmt=".2f")
            else:
                self.logger.debug("No valid pump data received.")
        except Exception as e:
            self.log_event("error", f"housekeeping read failed: {e}")
