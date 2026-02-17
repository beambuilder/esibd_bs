"""SW (Switch) base device class for CGC HV-AMX-CTRL-4ED."""

import ctypes
import json
import os


class SWBase:
    """SW base device class wrapping the COM-HVAMX4ED DLL."""

    # Error codes
    NO_ERR = 0
    ERR_PORT_RANGE = -1
    ERR_OPEN = -2
    ERR_CLOSE = -3
    ERR_PURGE = -4
    ERR_CONTROL = -5
    ERR_STATUS = -6
    ERR_COMMAND_SEND = -7
    ERR_DATA_SEND = -8
    ERR_TERM_SEND = -9
    ERR_COMMAND_RECEIVE = -10
    ERR_DATA_RECEIVE = -11
    ERR_TERM_RECEIVE = -12
    ERR_COMMAND_WRONG = -13
    ERR_ARGUMENT_WRONG = -14
    ERR_ARGUMENT = -15
    ERR_RATE = -16
    ERR_NOT_CONNECTED = -100
    ERR_NOT_READY = -101
    ERR_READY = -102
    ERR_DEBUG_OPEN = -400
    ERR_DEBUG_CLOSE = -401

    # Main state constants dictionary
    MAIN_STATE = {
        0x0000: 'STATE_ON',
        0x8000: 'STATE_ERROR',
        0x8001: 'STATE_ERR_VSUP',
        0x8002: 'STATE_ERR_TEMP_LOW',
        0x8003: 'STATE_ERR_TEMP_HIGH',
        0x8004: 'STATE_ERR_FPGA_DIS',
    }

    # Device state constants dictionary (bit flags)
    DEVICE_STATE = {
        (1 << 0x00): 'DEVST_VCPU_FAIL',
        (1 << 0x01): 'DEVST_VSUP_FAIL',
        (1 << 0x08): 'DEVST_FAN1_FAIL',
        (1 << 0x09): 'DEVST_FAN2_FAIL',
        (1 << 0x0A): 'DEVST_FAN3_FAIL',
        (1 << 0x0F): 'DEVST_FPGA_DIS',
        (1 << 0x10): 'DEVST_SEN1_HIGH',
        (1 << 0x11): 'DEVST_SEN2_HIGH',
        (1 << 0x12): 'DEVST_SEN3_HIGH',
        (1 << 0x18): 'DEVST_SEN1_LOW',
        (1 << 0x19): 'DEVST_SEN2_LOW',
        (1 << 0x1A): 'DEVST_SEN3_LOW',
    }

    # Controller state & configuration bits
    CONTROLLER_STATE = {
        (1 << 0):  'ENB',
        (1 << 1):  'ENB_OSC',
        (1 << 2):  'ENB_PULSER',
        (1 << 3):  'SW_TRIG',
        (1 << 4):  'SW_PULSE',
        (1 << 5):  'PREVENT_DIS',
        (1 << 6):  'DIS_DITHER',
        (1 << 7):  'NC',
        (1 << 8):  'ENABLE',
        (1 << 9):  'SW_TRIG_OUT',
        (1 << 10): 'CLRN',
    }

    # Pulser trigger/enable configuration input sources
    PULSER_CFG = {
        0:  'LOG0',
        1:  'SOFT_TRIG',
        2:  'OSC0',
        3:  'DIN0',
        4:  'DIN1',
        5:  'DIN2',
        6:  'DIN3',
        7:  'DIN4',
        8:  'DIN5',
        9:  'DIN6',
        10: 'PULS_OUT0',
        11: 'PULS_OUT1',
        12: 'PULS_OUT2',
        13: 'PULS_OUT3',
        14: 'PULS_RUN0',
        15: 'PULS_RUN1',
        16: 'PULS_RUN2',
        17: 'PULS_RUN3',
        18: 'CLK2M',
        19: 'CLK4M',
    }

    # Constants from header
    MAX_PORT = 16
    CLOCK = 100e6
    OSC_OFFSET = 2
    PULSER_NUM = 4
    PULSER_DELAY_OFFSET = 3
    PULSER_WIDTH_OFFSET = 2
    PULSER_BURST_NUM = 2
    MAX_BURST = (1 << 24)
    SWITCH_NUM = 4
    SWITCH_DELAY_SIZE = 4
    SWITCH_DELAY_MAX = (1 << 4)
    SWITCH_DELAY_MASK = (1 << 4) - 1
    MAPPING_SIZE = 4  # == SWITCH_NUM
    MAPPING_MAX = (1 << 4)
    MAPPING_MASK = (1 << 4) - 1
    MAPPING_NUM = 5  # SWITCH_NUM + 1
    DIO_NUM = 7
    DIO_INPUT_MAX = 20
    CONFIG_SIZE = 6
    CONFIG_MAX = (1 << 6)
    CONFIG_MASK = (1 << 6) - 1
    CONFIG_INV = (1 << 5)
    SELECT_MASK = (1 << 5) - 1
    CFG_INVERT = (1 << 5)
    CFG_MASK = 31
    PULSER_CFG_NUM = 6  # PULSER_NUM + PULSER_BURST_NUM
    PULSER_INPUT_MAX = 18
    SEN_COUNT = 3
    FAN_COUNT = 3
    FAN_PWM_MAX = 1000
    MAX_CONFIG = 126
    CONFIG_NAME_SIZE = 52

    def __init__(self, com, port=0, log=None, idn=""):
        """
        Initialization.

        Parameters
        ----------
        com : int
            COM Port Hardware Side.
        port : int
            Port number Software Side. Up to 16 devices can be used.
        log : logfile, optional
            Logging instance where information is logged.
        idn : str, optional
            String to append to class name to distinguish between same devices.

        """
        # Get the directory where this file is located
        self.class_dir = os.path.dirname(os.path.abspath(__file__))

        # Importing dll for hardware control
        self.sw_dll_path = os.path.join(
            self.class_dir, r"COM-HVAMX4ED_1-01\x64\COM-HVAMX4ED.dll"
        )
        self.sw_dll = ctypes.WinDLL(self.sw_dll_path)

        # Importing error messages
        self.err_path = os.path.join(os.path.dirname(self.class_dir), "error_codes.json")
        with open(self.err_path, "rb") as f:
            self.err_dict = json.load(f)

        self.com = com
        self.port = port
        self.log = log
        self.idn = idn

    # =========================================================================
    #     General
    # =========================================================================

    def get_sw_version(self):
        """
        Get the COM-HVAMX4ED software (DLL) version.

        Returns
        -------
        int
            Software version.

        """
        self.sw_dll.COM_HVAMX4ED_GetSWVersion.restype = ctypes.c_uint16
        version = self.sw_dll.COM_HVAMX4ED_GetSWVersion()
        return version

    def open_port(self, com_number, port_number=None):
        """
        Open communication link to device.

        Parameters
        ----------
        com_number : int
            COM port number (1 = COM1, 2 = COM2, etc.).
        port_number : int, optional
            Port number (default: self.port).

        Returns
        -------
        int
            Status code.

        """
        if port_number is None:
            port_number = self.port
        status = self.sw_dll.COM_HVAMX4ED_Open(port_number, com_number)
        return status

    def close_port(self):
        """
        Close the communication link.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_Close(self.port)
        return status

    def set_baud_rate(self, baud_rate):
        """
        Set communication speed.

        Parameters
        ----------
        baud_rate : int
            Baud rate value (usually set to max: 230400).

        Returns
        -------
        tuple
            (status, actual_baud_rate).

        """
        baud_rate_ref = ctypes.c_uint(baud_rate)
        status = self.sw_dll.COM_HVAMX4ED_SetBaudRate(
            self.port, ctypes.byref(baud_rate_ref)
        )
        return status, baud_rate_ref.value

    def purge(self):
        """
        Clear data buffers for the port.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_Purge(self.port)
        return status

    def device_purge(self):
        """
        Clear output data buffer of the device.

        Returns
        -------
        tuple
            (status, empty) where empty is True if buffer is empty.

        """
        empty = ctypes.c_bool()
        status = self.sw_dll.COM_HVAMX4ED_DevicePurge(
            self.port, ctypes.byref(empty)
        )
        return status, empty.value

    def get_buffer_state(self):
        """
        Return True if the input data buffer of the device is empty.

        Returns
        -------
        tuple
            (status, empty).

        """
        empty = ctypes.c_bool()
        status = self.sw_dll.COM_HVAMX4ED_GetBufferState(
            self.port, ctypes.byref(empty)
        )
        return status, empty.value

    # =========================================================================
    #     Device Control
    # =========================================================================

    def get_main_state(self):
        """
        Get the main device status.

        Returns
        -------
        tuple
            (status, state_hex, state_name).

        """
        state = ctypes.c_uint16()
        status = self.sw_dll.COM_HVAMX4ED_GetMainState(
            self.port, ctypes.byref(state)
        )
        state_value = state.value
        state_name = self.MAIN_STATE.get(
            state_value, f'UNKNOWN_STATE_0x{state_value:04X}'
        )
        return status, hex(state_value), state_name

    def get_device_state(self):
        """
        Get the device status (bit flags).

        Returns
        -------
        tuple
            (status, state_hex, state_names) where state_names is a list
            of active state flag names.

        """
        device_state = ctypes.c_uint32()
        status = self.sw_dll.COM_HVAMX4ED_GetDeviceState(
            self.port, ctypes.byref(device_state)
        )
        state_value = device_state.value

        active_states = []
        if state_value == 0:
            active_states.append('DEVST_OK')
        else:
            for flag, name in self.DEVICE_STATE.items():
                if state_value & flag:
                    active_states.append(name)

        return status, hex(state_value), active_states

    def get_housekeeping(self):
        """
        Get the housekeeping data.

        Returns
        -------
        tuple
            (status, volt_12v, volt_5v0, volt_3v3, temp_cpu).

        """
        volt_12v = ctypes.c_double()
        volt_5v0 = ctypes.c_double()
        volt_3v3 = ctypes.c_double()
        temp_cpu = ctypes.c_double()

        status = self.sw_dll.COM_HVAMX4ED_GetHousekeeping(
            self.port,
            ctypes.byref(volt_12v),
            ctypes.byref(volt_5v0),
            ctypes.byref(volt_3v3),
            ctypes.byref(temp_cpu),
        )
        return status, volt_12v.value, volt_5v0.value, volt_3v3.value, temp_cpu.value

    def get_sensor_data(self):
        """
        Get sensor data (3 temperature sensors).

        Returns
        -------
        tuple
            (status, temp0, temp1, temp2).

        """
        temperature = (ctypes.c_double * self.SEN_COUNT)()
        status = self.sw_dll.COM_HVAMX4ED_GetSensorData(self.port, temperature)
        return status, temperature[0], temperature[1], temperature[2]

    def get_fan_data(self):
        """
        Get fan data (3 fans).

        Returns
        -------
        tuple
            (status, enabled, failed, set_rpm, measured_rpm, pwm).

        """
        enabled = (ctypes.c_bool * self.FAN_COUNT)()
        failed = (ctypes.c_bool * self.FAN_COUNT)()
        set_rpm = (ctypes.c_uint16 * self.FAN_COUNT)()
        measured_rpm = (ctypes.c_uint16 * self.FAN_COUNT)()
        pwm = (ctypes.c_uint16 * self.FAN_COUNT)()

        status = self.sw_dll.COM_HVAMX4ED_GetFanData(
            self.port, enabled, failed, set_rpm, measured_rpm, pwm
        )
        return (
            status,
            [enabled[i] for i in range(self.FAN_COUNT)],
            [failed[i] for i in range(self.FAN_COUNT)],
            [set_rpm[i] for i in range(self.FAN_COUNT)],
            [measured_rpm[i] for i in range(self.FAN_COUNT)],
            [pwm[i] for i in range(self.FAN_COUNT)],
        )

    def get_led_data(self):
        """
        Get LED data.

        Returns
        -------
        tuple
            (status, red, green, blue).

        """
        red = ctypes.c_bool()
        green = ctypes.c_bool()
        blue = ctypes.c_bool()

        status = self.sw_dll.COM_HVAMX4ED_GetLEDData(
            self.port, ctypes.byref(red), ctypes.byref(green), ctypes.byref(blue)
        )
        return status, red.value, green.value, blue.value

    # =========================================================================
    #     Pulser Management
    # =========================================================================

    def get_oscillator_period(self):
        """
        Get oscillator period.

        Returns
        -------
        tuple
            (status, period).

        """
        period = ctypes.c_uint32()
        status = self.sw_dll.COM_HVAMX4ED_GetOscillatorPeriod(
            self.port, ctypes.byref(period)
        )
        return status, period.value

    def set_oscillator_period(self, period):
        """
        Set oscillator period.

        Parameters
        ----------
        period : int
            Oscillator period value.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetOscillatorPeriod(
            self.port, ctypes.c_uint32(period)
        )
        return status

    def get_pulser_delay(self, pulser_no):
        """
        Get pulse delay of specified pulser.

        Parameters
        ----------
        pulser_no : int
            Pulser number (0-3).

        Returns
        -------
        tuple
            (status, delay).

        """
        delay = ctypes.c_uint32()
        status = self.sw_dll.COM_HVAMX4ED_GetPulserDelay(
            self.port, pulser_no, ctypes.byref(delay)
        )
        return status, delay.value

    def set_pulser_delay(self, pulser_no, delay):
        """
        Set pulse delay of specified pulser.

        Parameters
        ----------
        pulser_no : int
            Pulser number (0-3).
        delay : int
            Delay value.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetPulserDelay(
            self.port, pulser_no, ctypes.c_uint32(delay)
        )
        return status

    def get_pulser_width(self, pulser_no):
        """
        Get pulse width of specified pulser.

        Parameters
        ----------
        pulser_no : int
            Pulser number (0-3).

        Returns
        -------
        tuple
            (status, width).

        """
        width = ctypes.c_uint32()
        status = self.sw_dll.COM_HVAMX4ED_GetPulserWidth(
            self.port, pulser_no, ctypes.byref(width)
        )
        return status, width.value

    def set_pulser_width(self, pulser_no, width):
        """
        Set pulse width of specified pulser.

        Parameters
        ----------
        pulser_no : int
            Pulser number (0-3).
        width : int
            Width value.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetPulserWidth(
            self.port, pulser_no, ctypes.c_uint32(width)
        )
        return status

    def get_pulser_burst(self, pulser_no):
        """
        Get burst size of specified pulser.

        Parameters
        ----------
        pulser_no : int
            Pulser number (0-1, only first PULSER_BURST_NUM pulsers support burst).

        Returns
        -------
        tuple
            (status, burst).

        """
        burst = ctypes.c_uint32()
        status = self.sw_dll.COM_HVAMX4ED_GetPulserBurst(
            self.port, pulser_no, ctypes.byref(burst)
        )
        return status, burst.value

    def set_pulser_burst(self, pulser_no, burst):
        """
        Set burst size of specified pulser.

        Parameters
        ----------
        pulser_no : int
            Pulser number (0-1).
        burst : int
            Burst size (max 2^24).

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetPulserBurst(
            self.port, pulser_no, ctypes.c_uint32(burst)
        )
        return status

    def get_pulser_config(self, pulser_cfg_no):
        """
        Get configuration of specified pulser.

        PulserCfgNo assignments:
            0 = trigger cfg of pulser #0
            1 = stop    cfg of pulser #0
            2 = trigger cfg of pulser #1
            3 = stop    cfg of pulser #1
            4 = trigger cfg of pulser #2
            5 = trigger cfg of pulser #3

        Parameters
        ----------
        pulser_cfg_no : int
            Pulser configuration number (0-5).

        Returns
        -------
        tuple
            (status, config).

        """
        config = ctypes.c_ubyte()
        status = self.sw_dll.COM_HVAMX4ED_GetPulserConfig(
            self.port, pulser_cfg_no, ctypes.byref(config)
        )
        return status, config.value

    def set_pulser_config(self, pulser_cfg_no, config):
        """
        Set configuration of specified pulser.

        Parameters
        ----------
        pulser_cfg_no : int
            Pulser configuration number (0-5).
        config : int
            Configuration value (6-bit: signal select + invert bit).

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetPulserConfig(
            self.port, pulser_cfg_no, ctypes.c_ubyte(config)
        )
        return status

    # =========================================================================
    #     Switch Management
    # =========================================================================

    def get_switch_trigger_config(self, switch_no):
        """
        Get configuration of specified switch trigger.

        Parameters
        ----------
        switch_no : int
            Switch number (0-3).

        Returns
        -------
        tuple
            (status, config).

        """
        config = ctypes.c_ubyte()
        status = self.sw_dll.COM_HVAMX4ED_GetSwitchTriggerConfig(
            self.port, switch_no, ctypes.byref(config)
        )
        return status, config.value

    def set_switch_trigger_config(self, switch_no, config):
        """
        Set configuration of specified switch trigger.

        Parameters
        ----------
        switch_no : int
            Switch number (0-3).
        config : int
            Configuration value.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetSwitchTriggerConfig(
            self.port, switch_no, ctypes.c_ubyte(config)
        )
        return status

    def get_switch_enable_config(self, switch_no):
        """
        Get configuration of specified switch enable.

        Parameters
        ----------
        switch_no : int
            Switch number (0-3).

        Returns
        -------
        tuple
            (status, config).

        """
        config = ctypes.c_ubyte()
        status = self.sw_dll.COM_HVAMX4ED_GetSwitchEnableConfig(
            self.port, switch_no, ctypes.byref(config)
        )
        return status, config.value

    def set_switch_enable_config(self, switch_no, config):
        """
        Set configuration of specified switch enable.

        Parameters
        ----------
        switch_no : int
            Switch number (0-3).
        config : int
            Configuration value.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetSwitchEnableConfig(
            self.port, switch_no, ctypes.c_ubyte(config)
        )
        return status

    def get_switch_trigger_delay(self, switch_no):
        """
        Get delays of specified switch trigger.

        Parameters
        ----------
        switch_no : int
            Switch number (0-3).

        Returns
        -------
        tuple
            (status, rise_delay, fall_delay).

        """
        rise_delay = ctypes.c_ubyte()
        fall_delay = ctypes.c_ubyte()
        status = self.sw_dll.COM_HVAMX4ED_GetSwitchTriggerDelay(
            self.port, switch_no, ctypes.byref(rise_delay), ctypes.byref(fall_delay)
        )
        return status, rise_delay.value, fall_delay.value

    def set_switch_trigger_delay(self, switch_no, rise_delay, fall_delay):
        """
        Set delays of specified switch trigger.

        Parameters
        ----------
        switch_no : int
            Switch number (0-3).
        rise_delay : int
            Rise delay (0 to SWITCH_DELAY_MAX-1).
        fall_delay : int
            Fall delay (0 to SWITCH_DELAY_MAX-1).

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetSwitchTriggerDelay(
            self.port, switch_no, ctypes.c_ubyte(rise_delay), ctypes.c_ubyte(fall_delay)
        )
        return status

    def get_switch_enable_delay(self, switch_no):
        """
        Get delay of specified switch enable.

        Parameters
        ----------
        switch_no : int
            Switch number (0-3).

        Returns
        -------
        tuple
            (status, delay).

        """
        delay = ctypes.c_ubyte()
        status = self.sw_dll.COM_HVAMX4ED_GetSwitchEnableDelay(
            self.port, switch_no, ctypes.byref(delay)
        )
        return status, delay.value

    def set_switch_enable_delay(self, switch_no, delay):
        """
        Set delay of specified switch enable.

        Parameters
        ----------
        switch_no : int
            Switch number (0-3).
        delay : int
            Delay value (0 to SWITCH_DELAY_MAX-1).

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetSwitchEnableDelay(
            self.port, switch_no, ctypes.c_ubyte(delay)
        )
        return status

    # =========================================================================
    #     Switch Mapping
    # =========================================================================

    def get_switch_trigger_mapping(self, mapping_no):
        """
        Get specified switch trigger mapping.

        Parameters
        ----------
        mapping_no : int
            Mapping number (0 to MAPPING_NUM-1).

        Returns
        -------
        tuple
            (status, mapping).

        """
        mapping = ctypes.c_ubyte()
        status = self.sw_dll.COM_HVAMX4ED_GetSwitchTriggerMapping(
            self.port, mapping_no, ctypes.byref(mapping)
        )
        return status, mapping.value

    def set_switch_trigger_mapping(self, mapping_no, mapping):
        """
        Set specified switch trigger mapping.

        Parameters
        ----------
        mapping_no : int
            Mapping number (0 to MAPPING_NUM-1).
        mapping : int
            Mapping value (bitmask for switches).

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetSwitchTriggerMapping(
            self.port, mapping_no, ctypes.c_ubyte(mapping)
        )
        return status

    def get_switch_enable_mapping(self, mapping_no):
        """
        Get specified switch enable mapping.

        Parameters
        ----------
        mapping_no : int
            Mapping number (0 to MAPPING_NUM-1).

        Returns
        -------
        tuple
            (status, mapping).

        """
        mapping = ctypes.c_ubyte()
        status = self.sw_dll.COM_HVAMX4ED_GetSwitchEnableMapping(
            self.port, mapping_no, ctypes.byref(mapping)
        )
        return status, mapping.value

    def set_switch_enable_mapping(self, mapping_no, mapping):
        """
        Set specified switch enable mapping.

        Parameters
        ----------
        mapping_no : int
            Mapping number (0 to MAPPING_NUM-1).
        mapping : int
            Mapping value (bitmask for switches).

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetSwitchEnableMapping(
            self.port, mapping_no, ctypes.c_ubyte(mapping)
        )
        return status

    def get_switch_trigger_mapping_enable(self):
        """
        Get the switch trigger mapping enable bit.

        Returns
        -------
        tuple
            (status, enable).

        """
        enable = ctypes.c_bool()
        status = self.sw_dll.COM_HVAMX4ED_GetSwitchTriggerMappingEnable(
            self.port, ctypes.byref(enable)
        )
        return status, enable.value

    def set_switch_trigger_mapping_enable(self, enable):
        """
        Set the switch trigger mapping enable bit.

        Parameters
        ----------
        enable : bool
            Enable state.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetSwitchTriggerMappingEnable(
            self.port, ctypes.c_bool(enable)
        )
        return status

    def get_switch_enable_mapping_enable(self):
        """
        Get the switch enable mapping enable bit.

        Returns
        -------
        tuple
            (status, enable).

        """
        enable = ctypes.c_bool()
        status = self.sw_dll.COM_HVAMX4ED_GetSwitchEnableMappingEnable(
            self.port, ctypes.byref(enable)
        )
        return status, enable.value

    def set_switch_enable_mapping_enable(self, enable):
        """
        Set the switch enable mapping enable bit.

        Parameters
        ----------
        enable : bool
            Enable state.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetSwitchEnableMappingEnable(
            self.port, ctypes.c_bool(enable)
        )
        return status

    # =========================================================================
    #     Digital I/O
    # =========================================================================

    def get_input_config(self):
        """
        Get configuration of digital inputs/outputs.

        Returns
        -------
        tuple
            (status, output_enable, termination_enable).

        """
        output_enable = ctypes.c_ubyte()
        termination_enable = ctypes.c_ubyte()
        status = self.sw_dll.COM_HVAMX4ED_GetInputConfig(
            self.port, ctypes.byref(output_enable), ctypes.byref(termination_enable)
        )
        return status, output_enable.value, termination_enable.value

    def set_input_config(self, output_enable, termination_enable):
        """
        Set configuration of digital inputs/outputs.

        Parameters
        ----------
        output_enable : int
            Output enable bitmask (7-bit for DIO_NUM channels).
        termination_enable : int
            Termination enable bitmask.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetInputConfig(
            self.port, ctypes.c_ubyte(output_enable), ctypes.c_ubyte(termination_enable)
        )
        return status

    def get_output_config(self, output_no):
        """
        Get configuration of specified output.

        Parameters
        ----------
        output_no : int
            Output number (0 to DIO_NUM-1).

        Returns
        -------
        tuple
            (status, configuration).

        """
        configuration = ctypes.c_ubyte()
        status = self.sw_dll.COM_HVAMX4ED_GetOutputConfig(
            self.port, output_no, ctypes.byref(configuration)
        )
        return status, configuration.value

    def set_output_config(self, output_no, configuration):
        """
        Set configuration of specified output.

        Parameters
        ----------
        output_no : int
            Output number (0 to DIO_NUM-1).
        configuration : int
            Configuration value.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetOutputConfig(
            self.port, output_no, ctypes.c_ubyte(configuration)
        )
        return status

    # =========================================================================
    #     Controller State & Configuration
    # =========================================================================

    def get_controller_state(self):
        """
        Get device state (combined state & configuration bits).

        Returns
        -------
        tuple
            (status, state_hex, state_names) where state_names is a list
            of active flag names.

        """
        state = ctypes.c_uint16()
        status = self.sw_dll.COM_HVAMX4ED_GetControllerState(
            self.port, ctypes.byref(state)
        )
        state_value = state.value

        active_states = []
        for flag, name in self.CONTROLLER_STATE.items():
            if state_value & flag:
                active_states.append(name)

        return status, hex(state_value), active_states

    def set_controller_config(self, config):
        """
        Set device configuration (lower 8 bits of controller state).

        Parameters
        ----------
        config : int
            Configuration byte value.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetControllerConfig(
            self.port, ctypes.c_ubyte(config)
        )
        return status

    # =========================================================================
    #     Configuration Management
    # =========================================================================

    def get_device_enable(self):
        """
        Get the enable state of the device.

        Returns
        -------
        tuple
            (status, enable).

        """
        enable = ctypes.c_bool()
        status = self.sw_dll.COM_HVAMX4ED_GetDeviceEnable(
            self.port, ctypes.byref(enable)
        )
        return status, enable.value

    def set_device_enable(self, enable):
        """
        Set the enable state of the device.

        Parameters
        ----------
        enable : bool
            Enable state.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetDeviceEnable(
            self.port, ctypes.c_bool(enable)
        )
        return status

    def reset_current_config(self):
        """
        Reset current configuration.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_ResetCurrentConfig(self.port)
        return status

    def save_current_config(self, config_number):
        """
        Save current configuration to NVM.

        Parameters
        ----------
        config_number : int
            Configuration number (0 to MAX_CONFIG-1).

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SaveCurrentConfig(
            self.port, config_number
        )
        return status

    def load_current_config(self, config_number):
        """
        Load current configuration from NVM.

        Parameters
        ----------
        config_number : int
            Configuration number (0 to MAX_CONFIG-1).

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_LoadCurrentConfig(
            self.port, config_number
        )
        return status

    def get_config_name(self, config_number):
        """
        Get configuration name.

        Parameters
        ----------
        config_number : int
            Configuration number (0 to MAX_CONFIG-1).

        Returns
        -------
        tuple
            (status, name).

        """
        name = ctypes.create_string_buffer(self.CONFIG_NAME_SIZE)
        status = self.sw_dll.COM_HVAMX4ED_GetConfigName(
            self.port, config_number, name
        )
        return status, name.value.decode()

    def set_config_name(self, config_number, name):
        """
        Set configuration name.

        Parameters
        ----------
        config_number : int
            Configuration number (0 to MAX_CONFIG-1).
        name : str
            Configuration name (max CONFIG_NAME_SIZE-1 characters).

        Returns
        -------
        int
            Status code.

        """
        name_buffer = ctypes.create_string_buffer(
            name.encode(), self.CONFIG_NAME_SIZE
        )
        status = self.sw_dll.COM_HVAMX4ED_SetConfigName(
            self.port, config_number, name_buffer
        )
        return status

    def get_config_flags(self, config_number):
        """
        Get configuration flags.

        Parameters
        ----------
        config_number : int
            Configuration number (0 to MAX_CONFIG-1).

        Returns
        -------
        tuple
            (status, active, valid).

        """
        active = ctypes.c_bool()
        valid = ctypes.c_bool()
        status = self.sw_dll.COM_HVAMX4ED_GetConfigFlags(
            self.port, config_number, ctypes.byref(active), ctypes.byref(valid)
        )
        return status, active.value, valid.value

    def set_config_flags(self, config_number, active, valid):
        """
        Set configuration flags.

        Parameters
        ----------
        config_number : int
            Configuration number (0 to MAX_CONFIG-1).
        active : bool
            Active flag.
        valid : bool
            Valid flag.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_SetConfigFlags(
            self.port, config_number, ctypes.c_bool(active), ctypes.c_bool(valid)
        )
        return status

    def get_config_list(self):
        """
        Get configuration list.

        Returns
        -------
        tuple
            (status, active_list, valid_list) where lists contain MAX_CONFIG
            boolean values.

        """
        active = (ctypes.c_bool * self.MAX_CONFIG)()
        valid = (ctypes.c_bool * self.MAX_CONFIG)()
        status = self.sw_dll.COM_HVAMX4ED_GetConfigList(self.port, active, valid)
        return (
            status,
            [active[i] for i in range(self.MAX_CONFIG)],
            [valid[i] for i in range(self.MAX_CONFIG)],
        )

    # =========================================================================
    #     System
    # =========================================================================

    def restart(self):
        """
        Restart the controller.

        Returns
        -------
        int
            Status code.

        """
        status = self.sw_dll.COM_HVAMX4ED_Restart(self.port)
        return status

    def get_cpu_data(self):
        """
        Get CPU load (0-1) and frequency (Hz).

        Returns
        -------
        tuple
            (status, load, frequency).

        """
        load = ctypes.c_double()
        frequency = ctypes.c_double()
        status = self.sw_dll.COM_HVAMX4ED_GetCPUData(
            self.port, ctypes.byref(load), ctypes.byref(frequency)
        )
        return status, load.value, frequency.value

    def get_uptime(self):
        """
        Get device uptime and operation time.

        Returns
        -------
        tuple
            (status, seconds, milliseconds, optime).

        """
        seconds = ctypes.c_uint32()
        milliseconds = ctypes.c_uint16()
        optime = ctypes.c_uint32()
        status = self.sw_dll.COM_HVAMX4ED_GetUptime(
            self.port,
            ctypes.byref(seconds),
            ctypes.byref(milliseconds),
            ctypes.byref(optime),
        )
        return status, seconds.value, milliseconds.value, optime.value

    def get_total_time(self):
        """
        Get total device uptime and operation time.

        Returns
        -------
        tuple
            (status, uptime, optime).

        """
        uptime = ctypes.c_uint32()
        optime = ctypes.c_uint32()
        status = self.sw_dll.COM_HVAMX4ED_GetTotalTime(
            self.port, ctypes.byref(uptime), ctypes.byref(optime)
        )
        return status, uptime.value, optime.value

    def get_hw_type(self):
        """
        Get the hardware type.

        Returns
        -------
        tuple
            (status, hw_type).

        """
        hw_type = ctypes.c_uint16()
        status = self.sw_dll.COM_HVAMX4ED_GetHWType(
            self.port, ctypes.byref(hw_type)
        )
        return status, hw_type.value

    def get_hw_version(self):
        """
        Get the hardware version.

        Returns
        -------
        tuple
            (status, hw_version).

        """
        hw_version = ctypes.c_uint16()
        status = self.sw_dll.COM_HVAMX4ED_GetHWVersion(
            self.port, ctypes.byref(hw_version)
        )
        return status, hw_version.value

    def get_fw_version(self):
        """
        Get the firmware version.

        Returns
        -------
        tuple
            (status, version).

        """
        version = ctypes.c_uint16()
        status = self.sw_dll.COM_HVAMX4ED_GetFWVersion(
            self.port, ctypes.byref(version)
        )
        return status, version.value

    def get_fw_date(self):
        """
        Get the firmware date.

        Returns
        -------
        tuple
            (status, date_string).

        """
        date_string = ctypes.create_string_buffer(16)
        status = self.sw_dll.COM_HVAMX4ED_GetFWDate(self.port, date_string)
        return status, date_string.value.decode()

    def get_product_id(self):
        """
        Get the product identification.

        Returns
        -------
        tuple
            (status, identification).

        """
        identification = ctypes.create_string_buffer(60)
        status = self.sw_dll.COM_HVAMX4ED_GetProductID(self.port, identification)
        return status, identification.value.decode()

    def get_product_no(self):
        """
        Get the product number.

        Returns
        -------
        tuple
            (status, number).

        """
        number = ctypes.c_uint32()
        status = self.sw_dll.COM_HVAMX4ED_GetProductNo(
            self.port, ctypes.byref(number)
        )
        return status, number.value

    # =========================================================================
    #     Communication Port Status
    # =========================================================================

    def get_interface_state(self):
        """
        Get software interface state.

        Returns
        -------
        int
            Interface state code.

        """
        state = self.sw_dll.COM_HVAMX4ED_GetInterfaceState(self.port)
        return state

    def get_error_message(self):
        """
        Get the error message corresponding to the software interface state.

        Returns
        -------
        str
            Error message.

        """
        self.sw_dll.COM_HVAMX4ED_GetErrorMessage.restype = ctypes.c_char_p
        msg_ptr = self.sw_dll.COM_HVAMX4ED_GetErrorMessage(self.port)
        message = msg_ptr.decode() if msg_ptr else "No error"
        return message

    def get_io_state(self):
        """
        Get serial port interface state.

        Returns
        -------
        int
            IO state code.

        """
        state = self.sw_dll.COM_HVAMX4ED_GetIOState(self.port)
        return state

    def get_io_error_message(self):
        """
        Get the error message corresponding to the serial port interface state.

        Returns
        -------
        str
            Error message.

        """
        self.sw_dll.COM_HVAMX4ED_GetIOErrorMessage.restype = ctypes.c_char_p
        msg_ptr = self.sw_dll.COM_HVAMX4ED_GetIOErrorMessage(self.port)
        message = msg_ptr.decode() if msg_ptr else "No error"
        return message
