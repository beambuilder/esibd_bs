"""
HiPace accessory-port configuration (TC400/TC80/TC110) and the HiPace80DCU
TC110 housekeeping table.

Accessory configs: params 35/36(/37/38 on TC400; /68/69 on TC80), plus the
TC110-only digital output DO1 (param 24). The dashboard dropdowns read the
Cfg_* hk channels and write through the set_cfg_* methods, so every class
needs: valid-range enforcement per drive, a stateful simulation roundtrip,
and the Cfg_* channels present in HK_CHANNELS/_sim_channels.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from devices.pfeiffer.hipacebus import HiPace80Bus, HiPace80DCU, HiPace300Bus


@pytest.fixture
def tc400():
    return HiPace300Bus("HiPace_Transfer", port="COM95", test_mode=True)


@pytest.fixture
def tc80():
    return HiPace80Bus("HiPace_LL_PhotonSTM", port="COM96", test_mode=True)


@pytest.fixture
def tc110():
    return HiPace80DCU("HiPace_LL_MPI", port="COM97", test_mode=True)


class TestValidRanges:
    """Each drive rejects the config values its manual does not list."""

    def test_tc400_rejects_11(self, tc400):
        with pytest.raises(ValueError):
            tc400.set_cfg_acc_a1(11)

    def test_tc400_accepts_full_range(self, tc400):
        for v in (0, 9, 10, 12, 14):
            tc400.set_cfg_acc_b2(v)
            assert tc400.get_cfg_acc_b2() == v

    @pytest.mark.parametrize("bad", [9, 10, 11, 14])
    def test_tc80_rejects_tc400_only_values(self, tc80, bad):
        with pytest.raises(ValueError):
            tc80.set_cfg_acc_c1(bad)

    def test_tc110_accepts_tc400_range(self, tc110):
        for v in (9, 10, 14):
            tc110.set_cfg_acc_b1(v)
            assert tc110.get_cfg_acc_b1() == v

    def test_tc110_rejects_11(self, tc110):
        with pytest.raises(ValueError):
            tc110.set_cfg_acc_a1(11)

    @pytest.mark.parametrize("bad", [-1, 23])
    def test_do1_range(self, tc110, bad):
        with pytest.raises(ValueError):
            tc110.set_cfg_do1(bad)


class TestSimRoundtrip:
    """Simulated set -> get roundtrips keep the integer value (the sim
    write path must not collapse u_short_int params to bool)."""

    def test_tc400_defaults_mirror_lab(self, tc400):
        assert [tc400.get_cfg_acc_a1(), tc400.get_cfg_acc_b1(),
                tc400.get_cfg_acc_a2(), tc400.get_cfg_acc_b2()] == [2, 6, 6, 6]

    def test_tc80_defaults_mirror_photon_stm(self, tc80):
        assert [tc80.get_cfg_acc_a1(), tc80.get_cfg_acc_b1(),
                tc80.get_cfg_acc_c1(), tc80.get_cfg_acc_d1()] == [2, 13, 1, 13]

    def test_tc110_defaults_mirror_mpi(self, tc110):
        assert [tc110.get_cfg_acc_a1(), tc110.get_cfg_acc_b1(),
                tc110.get_cfg_do1()] == [1, 2, 0]

    def test_roundtrip_keeps_integer(self, tc400):
        tc400.set_cfg_acc_a1(13)
        assert tc400.get_cfg_acc_a1() == 13

    def test_do1_roundtrip(self, tc110):
        tc110.set_cfg_do1(22)
        assert tc110.get_cfg_do1() == 22

    def test_boolean_params_stay_bool(self, tc400):
        tc400.enable_heating()
        assert tc400._sim_state["heating"] is True


class TestHkChannels:
    """Cfg_* channels ride housekeeping; the TC110 table drops the TC80
    parameters the TC110 manual does not define (hk aborts at the first
    failing channel, so a NO_DEF parameter would black-hole the rest)."""

    TC110_MISSING = (
        "Temperature_Management", "Temp_Power_Stage", "Temp_Rotor",
        "Pump_Identification", "Max_Power_Output_Time", "Fan_On_Temperature",
        "Power_Output_Voltage", "Power_Output_Threshold",
        "Cfg_Acc_C1", "Cfg_Acc_D1",
    )

    def test_cfg_channels_in_tables(self):
        names300 = [c[0] for c in HiPace300Bus.HK_CHANNELS]
        names80 = [c[0] for c in HiPace80Bus.HK_CHANNELS]
        names110 = [c[0] for c in HiPace80DCU.HK_CHANNELS]
        assert {"Cfg_Acc_A1", "Cfg_Acc_B1", "Cfg_Acc_A2", "Cfg_Acc_B2"} <= set(names300)
        assert {"Cfg_Acc_A1", "Cfg_Acc_B1", "Cfg_Acc_C1", "Cfg_Acc_D1"} <= set(names80)
        assert {"Cfg_Acc_A1", "Cfg_Acc_B1", "Cfg_DO1"} <= set(names110)

    def test_tc110_drops_missing_params(self):
        names110 = set(c[0] for c in HiPace80DCU.HK_CHANNELS)
        assert not names110 & set(self.TC110_MISSING)

    def test_tc110_gains_bearing_and_motor_temp(self):
        names110 = [c[0] for c in HiPace80DCU.HK_CHANNELS]
        assert "Temp_Bearing" in names110 and "Temp_Motor" in names110

    @pytest.mark.parametrize("cls", [HiPace300Bus, HiPace80Bus, HiPace80DCU])
    def test_sim_covers_every_hk_channel(self, cls):
        dev = cls("sim_dev", port="COM98", test_mode=True)
        sim = dev._sim_channels()
        missing = [c[0] for c in dev.HK_CHANNELS if c[0] not in sim]
        assert not missing

    def test_hk_cycle_logs_cfg_channels(self, tc110):
        logged = []
        tc110.log_sample = lambda channel, value, unit="", fmt="": logged.append(
            (channel, value))
        tc110.hk_monitor()
        by_name = dict(logged)
        assert by_name["Cfg_Acc_A1"] == 1
        assert by_name["Cfg_Acc_B1"] == 2
        assert by_name["Cfg_DO1"] == 0
