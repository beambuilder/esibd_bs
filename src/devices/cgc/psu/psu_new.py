"""PSU (Power Supply Unit) device class for CGC."""

import ctypes
import json
import os

class PSU:
    """PSU device class."""
    
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
    
    # Main state constants
    STATE_ON = 0x0000
    STATE_ERROR = 0x8000
    STATE_ERR_VSUP = 0x8001
    STATE_ERR_TEMP_LOW = 0x8002
    STATE_ERR_TEMP_HIGH = 0x8003
    STATE_ERR_ILOCK = 0x8004
    STATE_ERR_PSU_DIS = 0x8005
    
    # Device state constants
    DEVST_OK = 0
    DEVST_VCPU_FAIL = (1 << 0x00)
    DEVST_VFAN_FAIL = (1 << 0x01)
    DEVST_VPSU0_FAIL = (1 << 0x02)
    DEVST_VPSU1_FAIL = (1 << 0x03)
    DEVST_FAN1_FAIL = (1 << 0x08)
    DEVST_FAN2_FAIL = (1 << 0x09)
    DEVST_FAN3_FAIL = (1 << 0x0A)
    DEVST_PSU_DIS = (1 << 0x0F)
    DEVST_SEN1_HIGH = (1 << 0x10)
    DEVST_SEN2_HIGH = (1 << 0x11)
    DEVST_SEN3_HIGH = (1 << 0x12)
    DEVST_SEN1_LOW = (1 << 0x18)
    DEVST_SEN2_LOW = (1 << 0x19)
    DEVST_SEN3_LOW = (1 << 0x1A)
    
    # PSU state constants
    ST_ILIM_CTRL = (1 << 0)
    ST_LED_CTRL_R = (1 << 1)
    ST_LED_CTRL_G = (1 << 2)
    ST_LED_CTRL_B = (1 << 3)
    ST_PSU0_ENB_CTRL = (1 << 4)
    ST_PSU1_ENB_CTRL = (1 << 5)
    ST_PSU0_FULL_CTRL = (1 << 6)
    ST_PSU1_FULL_CTRL = (1 << 7)
    ST_ILOCK_OUT_DIS = (1 << 8)
    ST_ILOCK_BNC_DIS = (1 << 9)
    ST_PSU_ENB_CTRL = (1 << 10)
    ST_ILIM_ACT = (1 << 12)
    ST_PSU0_FULL_ACT = (1 << 13)
    ST_PSU1_FULL_ACT = (1 << 14)
    ST_RES_N = (1 << 15)
    ST_ILOCK_OUT_ACT = (1 << 16)
    ST_ILOCK_BNC_ACT = (1 << 17)
    ST_ILOCK_ACT = (1 << 18)
    ST_PSU_ENB_ACT = (1 << 19)
    ST_PSU0_ENB_ACT = (1 << 20)
    ST_PSU1_ENB_ACT = (1 << 21)
    ST_ILOCK_OUT = (1 << 22)
    ST_ILOCK_BNC = (1 << 23)
    
    # PSU numbers
    PSU_POS = 0
    PSU_NEG = 1
    PSU_NUM = 2
    
    # Sensor numbers
    SEN_NEG = 0
    SEN_MID = 1
    SEN_POS = 2
    SEN_COUNT = 3
    
    # Fan constants
    FAN_COUNT = 3
    FAN_PWM_MAX = 1000
    
    # Configuration
    MAX_CONFIG = 168
    CONFIG_NAME_SIZE = 75

    def __init__(self, com, port, log=None, idn=""):
        """
        Initialization

        Parameters
        ----------
        com : int
            COM Port Hardware Side
        port : int
            Portnumber Software Side. Up to 16 devices can be used
        log : logfile, optional
            Logging instance where information is logged
        idn : string, optional
            string to append to class name to distinguish between same devices. The default is empty.

        Returns
        -------
        None.

        """
        
        # Get the directory where this file (psu.py) is located
        self.class_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Importing dll for hardware control - path relative to psu.py
        self.psu_dll_path = os.path.join(self.class_dir, r"PSU-CTRL-2D_1-01\x64\COM-HVPSU2D.dll")
        self.rf_psu_dll = ctypes.WinDLL(self.psu_dll_path)

        # Importing error messages. See PSU manual - path relative to cgc folder
        self.err_path = os.path.join(os.path.dirname(self.class_dir), "error_codes.json")
        with open(self.err_path, "rb") as f:
            self.err_dict = json.load(f)

        self.com = com
        self.port = port
        self.log = log
        self.idn = idn

    def open_port(self, com, port):
        """
        Opening communication link to device

        Parameters
        ----------
        com : int
            com port.
        port : int
            port number.
        Returns
        -------
        int
            Status code.

        """
        status = self.rf_psu_dll.COM_HVPSU2D_Open(port, com)
        return status

    def close_port(self):
        """
        closing the communication link

        Returns
        -------
        int
            Status code.

        """
        status = self.rf_psu_dll.COM_HVPSU2D_Close(self.port)
        return status

    def set_comspeed(self, baudrate):
        """
        set communication speed. usually set to max: 230400

        Parameters
        ----------
        baudrate : int.

        Returns
        -------
        int
            Status code.

        """
        comspeed = ctypes.c_uint32(baudrate)
        status = self.rf_psu_dll.COM_HVPSU2D_SetBaudRate(self.port, ctypes.byref(comspeed))
        return status

    def purge(self):
        """
        Clear data buffers for the port.

        Returns
        -------
        int
            Status code.

        """
        status = self.rf_psu_dll.COM_HVPSU2D_Purge(self.port)
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
        status = self.rf_psu_dll.COM_HVPSU2D_DevicePurge(self.port, ctypes.byref(empty))
        return status, empty.value

    def get_buffer_state(self):
        """
        Return true if the input data buffer of the device is empty.

        Returns
        -------
        tuple
            (status, empty) where empty is True if buffer is empty.

        """
        empty = ctypes.c_bool()
        status = self.rf_psu_dll.COM_HVPSU2D_GetBufferState(self.port, ctypes.byref(empty))
        return status, empty.value

    # Device control
    
    def set_interlock_enable(self, con_out, con_bnc):
        """
        Set interlock enable for the output and the BNC connectors.

        Parameters
        ----------
        con_out : bool
            Enable interlock for output connector.
        con_bnc : bool
            Enable interlock for BNC connector.

        Returns
        -------
        int
            Status code.

        """
        status = self.rf_psu_dll.COM_HVPSU2D_SetInterlockEnable(
            self.port, ctypes.c_bool(con_out), ctypes.c_bool(con_bnc))
        return status

    def get_interlock_enable(self):
        """
        Get interlock enable for the output and the BNC connectors.

        Returns
        -------
        tuple
            (status, con_out, con_bnc).

        """
        con_out = ctypes.c_bool()
        con_bnc = ctypes.c_bool()
        status = self.rf_psu_dll.COM_HVPSU2D_GetInterlockEnable(
            self.port, ctypes.byref(con_out), ctypes.byref(con_bnc))
        return status, con_out.value, con_bnc.value

    def get_main_state(self):
        """
        Get the main device status.

        Returns
        -------
        tuple
            (status, state) where state is one of the STATE_* constants.

        """
        state = ctypes.c_uint16()
        status = self.rf_psu_dll.COM_HVPSU2D_GetMainState(self.port, ctypes.byref(state))
        return status, state.value

    def get_device_state(self):
        """
        Get the device status.

        Returns
        -------
        tuple
            (status, device_state) where device_state is a bitmask of DEVST_* flags.

        """
        device_state = ctypes.c_uint32()
        status = self.rf_psu_dll.COM_HVPSU2D_GetDeviceState(self.port, ctypes.byref(device_state))
        return status, device_state.value

    def get_housekeeping(self):
        """
        Get the housekeeping data.

        Returns
        -------
        tuple
            (status, volt_rect, volt_5v0, volt_3v3, temp_cpu).

        """
        volt_rect = ctypes.c_double()
        volt_5v0 = ctypes.c_double()
        volt_3v3 = ctypes.c_double()
        temp_cpu = ctypes.c_double()
        
        status = self.rf_psu_dll.COM_HVPSU2D_GetHousekeeping(
            self.port, ctypes.byref(volt_rect), ctypes.byref(volt_5v0), 
            ctypes.byref(volt_3v3), ctypes.byref(temp_cpu))
        
        return status, volt_rect.value, volt_5v0.value, volt_3v3.value, temp_cpu.value

    def get_sensor_data(self):
        """
        Get sensor data (3 temperature sensors).

        Returns
        -------
        tuple
            (status, temperatures) where temperatures is a list of 3 values.

        """
        temperature = (ctypes.c_double * 3)()
        status = self.rf_psu_dll.COM_HVPSU2D_GetSensorData(self.port, temperature)
        temps = [temperature[i] for i in range(3)]
        return status, temps

    def get_fan_data(self):
        """
        Get fan data (3 fans).

        Returns
        -------
        tuple
            (status, enabled, failed, set_rpm, measured_rpm, pwm).

        """
        enabled = (ctypes.c_bool * 3)()
        failed = (ctypes.c_bool * 3)()
        set_rpm = (ctypes.c_uint16 * 3)()
        measured_rpm = (ctypes.c_uint16 * 3)()
        pwm = (ctypes.c_uint16 * 3)()
        
        status = self.rf_psu_dll.COM_HVPSU2D_GetFanData(
            self.port, enabled, failed, set_rpm, measured_rpm, pwm)
        
        return (status, [enabled[i] for i in range(3)], [failed[i] for i in range(3)],
                [set_rpm[i] for i in range(3)], [measured_rpm[i] for i in range(3)],
                [pwm[i] for i in range(3)])

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
        
        status = self.rf_psu_dll.COM_HVPSU2D_GetLEDData(
            self.port, ctypes.byref(red), ctypes.byref(green), ctypes.byref(blue))
        
        return status, red.value, green.value, blue.value

    # PSU Management - Monitoring
    
    def get_adc_housekeeping(self, psu_num):
        """
        Get ADC housekeeping data.

        Parameters
        ----------
        psu_num : int
            PSU number (0 for positive, 1 for negative).

        Returns
        -------
        tuple
            (status, volt_avdd, volt_dvdd, volt_aldo, volt_dldo, volt_ref, temp_adc).

        """
        volt_avdd = ctypes.c_double()
        volt_dvdd = ctypes.c_double()
        volt_aldo = ctypes.c_double()
        volt_dldo = ctypes.c_double()
        volt_ref = ctypes.c_double()
        temp_adc = ctypes.c_double()
        
        status = self.rf_psu_dll.COM_HVPSU2D_GetADCHousekeeping(
            self.port, psu_num, ctypes.byref(volt_avdd), ctypes.byref(volt_dvdd),
            ctypes.byref(volt_aldo), ctypes.byref(volt_dldo), ctypes.byref(volt_ref),
            ctypes.byref(temp_adc))
        
        return (status, volt_avdd.value, volt_dvdd.value, volt_aldo.value,
                volt_dldo.value, volt_ref.value, temp_adc.value)

    def get_psu0_adc_housekeeping(self):
        """Get ADC housekeeping data for PSU0 (positive)."""
        return self.get_adc_housekeeping(self.PSU_POS)
    
    def get_psu1_adc_housekeeping(self):
        """Get ADC housekeeping data for PSU1 (negative)."""
        return self.get_adc_housekeeping(self.PSU_NEG)

    def get_psu_housekeeping(self, psu_num):
        """
        Get PSU housekeeping data.

        Parameters
        ----------
        psu_num : int
            PSU number (0 for positive, 1 for negative).

        Returns
        -------
        tuple
            (status, volt_24vp, volt_12vp, volt_12vn, volt_ref).

        """
        volt_24vp = ctypes.c_double()
        volt_12vp = ctypes.c_double()
        volt_12vn = ctypes.c_double()
        volt_ref = ctypes.c_double()
        
        status = self.rf_psu_dll.COM_HVPSU2D_GetPSUHousekeeping(
            self.port, psu_num, ctypes.byref(volt_24vp), ctypes.byref(volt_12vp),
            ctypes.byref(volt_12vn), ctypes.byref(volt_ref))
        
        return status, volt_24vp.value, volt_12vp.value, volt_12vn.value, volt_ref.value

    def get_psu0_housekeeping(self):
        """Get housekeeping data for PSU0 (positive)."""
        return self.get_psu_housekeeping(self.PSU_POS)
    
    def get_psu1_housekeeping(self):
        """Get housekeeping data for PSU1 (negative)."""
        return self.get_psu_housekeeping(self.PSU_NEG)

    def get_psu_data(self, psu_num):
        """
        Get measured PSU values.

        Parameters
        ----------
        psu_num : int
            PSU number (0 for positive, 1 for negative).

        Returns
        -------
        tuple
            (status, voltage, current, volt_dropout).

        """
        voltage = ctypes.c_double()
        current = ctypes.c_double()
        volt_dropout = ctypes.c_double()
        
        status = self.rf_psu_dll.COM_HVPSU2D_GetPSUData(
            self.port, psu_num, ctypes.byref(voltage), ctypes.byref(current),
            ctypes.byref(volt_dropout))
        
        return status, voltage.value, current.value, volt_dropout.value

    def get_psu0_data(self):
        """Get measured values for PSU0 (positive)."""
        return self.get_psu_data(self.PSU_POS)
    
    def get_psu1_data(self):
        """Get measured values for PSU1 (negative)."""
        return self.get_psu_data(self.PSU_NEG)

    # PSU Management - Control
    
    def set_psu_output_voltage(self, psu_num, voltage):
        """
        Set PSU output voltage.

        Parameters
        ----------
        psu_num : int
            PSU number (0 for positive, 1 for negative).
        voltage : float
            Voltage to set.

        Returns
        -------
        int
            Status code.

        """
        status = self.rf_psu_dll.COM_HVPSU2D_SetPSUOutputVoltage(
            self.port, psu_num, ctypes.c_double(voltage))
        return status

    def set_psu0_output_voltage(self, voltage):
        """Set PSU0 (positive) output voltage."""
        return self.set_psu_output_voltage(self.PSU_POS, voltage)
    
    def set_psu1_output_voltage(self, voltage):
        """Set PSU1 (negative) output voltage."""
        return self.set_psu_output_voltage(self.PSU_NEG, voltage)

    def get_psu_output_voltage(self, psu_num):
        """
        Get PSU output voltage.

        Parameters
        ----------
        psu_num : int
            PSU number (0 for positive, 1 for negative).

        Returns
        -------
        tuple
            (status, voltage).

        """
        voltage = ctypes.c_double()
        status = self.rf_psu_dll.COM_HVPSU2D_GetPSUOutputVoltage(
            self.port, psu_num, ctypes.byref(voltage))
        return status, voltage.value

    def get_psu0_output_voltage(self):
        """Get PSU0 (positive) output voltage."""
        return self.get_psu_output_voltage(self.PSU_POS)
    
    def get_psu1_output_voltage(self):
        """Get PSU1 (negative) output voltage."""
        return self.get_psu_output_voltage(self.PSU_NEG)

    def get_psu_set_output_voltage(self, psu_num):
        """
        Get PSU set & limit output voltage.

        Parameters
        ----------
        psu_num : int
            PSU number (0 for positive, 1 for negative).

        Returns
        -------
        tuple
            (status, voltage_set, voltage_limit).

        """
        voltage_set = ctypes.c_double()
        voltage_limit = ctypes.c_double()
        
        status = self.rf_psu_dll.COM_HVPSU2D_GetPSUSetOutputVoltage(
            self.port, psu_num, ctypes.byref(voltage_set), ctypes.byref(voltage_limit))
        
        return status, voltage_set.value, voltage_limit.value

    def get_psu0_set_output_voltage(self):
        """Get PSU0 (positive) set & limit output voltage."""
        return self.get_psu_set_output_voltage(self.PSU_POS)
    
    def get_psu1_set_output_voltage(self):
        """Get PSU1 (negative) set & limit output voltage."""
        return self.get_psu_set_output_voltage(self.PSU_NEG)

    def set_psu_output_current(self, psu_num, current):
        """
        Set PSU output current.

        Parameters
        ----------
        psu_num : int
            PSU number (0 for positive, 1 for negative).
        current : float
            Current to set.

        Returns
        -------
        int
            Status code.

        """
        status = self.rf_psu_dll.COM_HVPSU2D_SetPSUOutputCurrent(
            self.port, psu_num, ctypes.c_double(current))
        return status

    def set_psu0_output_current(self, current):
        """Set PSU0 (positive) output current."""
        return self.set_psu_output_current(self.PSU_POS, current)
    
    def set_psu1_output_current(self, current):
        """Set PSU1 (negative) output current."""
        return self.set_psu_output_current(self.PSU_NEG, current)

    def get_psu_output_current(self, psu_num):
        """
        Get PSU output current.

        Parameters
        ----------
        psu_num : int
            PSU number (0 for positive, 1 for negative).

        Returns
        -------
        tuple
            (status, current).

        """
        current = ctypes.c_double()
        status = self.rf_psu_dll.COM_HVPSU2D_GetPSUOutputCurrent(
            self.port, psu_num, ctypes.byref(current))
        return status, current.value

    def get_psu0_output_current(self):
        """Get PSU0 (positive) output current."""
        return self.get_psu_output_current(self.PSU_POS)
    
    def get_psu1_output_current(self):
        """Get PSU1 (negative) output current."""
        return self.get_psu_output_current(self.PSU_NEG)

    def get_psu_set_output_current(self, psu_num):
        """
        Get PSU set & limit output current.

        Parameters
        ----------
        psu_num : int
            PSU number (0 for positive, 1 for negative).

        Returns
        -------
        tuple
            (status, current_set, current_limit).

        """
        current_set = ctypes.c_double()
        current_limit = ctypes.c_double()
        
        status = self.rf_psu_dll.COM_HVPSU2D_GetPSUSetOutputCurrent(
            self.port, psu_num, ctypes.byref(current_set), ctypes.byref(current_limit))
        
        return status, current_set.value, current_limit.value

    def get_psu0_set_output_current(self):
        """Get PSU0 (positive) set & limit output current."""
        return self.get_psu_set_output_current(self.PSU_POS)
    
    def get_psu1_set_output_current(self):
        """Get PSU1 (negative) set & limit output current."""
        return self.get_psu_set_output_current(self.PSU_NEG)

    # PSU Management - Configuration
    
    def set_psu_enable(self, psu0, psu1):
        """
        Set PSU enable.

        Parameters
        ----------
        psu0 : bool
            Enable PSU 0 (positive).
        psu1 : bool
            Enable PSU 1 (negative).

        Returns
        -------
        int
            Status code.

        """
        status = self.rf_psu_dll.COM_HVPSU2D_SetPSUEnable(
            self.port, ctypes.c_bool(psu0), ctypes.c_bool(psu1))
        return status

    def set_psu0_enable(self, enable):
        """Set PSU0 (positive) enable state."""
        _, _, current_psu1 = self.get_psu_enable()
        return self.set_psu_enable(enable, current_psu1)
    
    def set_psu1_enable(self, enable):
        """Set PSU1 (negative) enable state."""
        _, current_psu0, _ = self.get_psu_enable()
        return self.set_psu_enable(current_psu0, enable)

    def get_psu_enable(self):
        """
        Get PSU enable.

        Returns
        -------
        tuple
            (status, psu0, psu1).

        """
        psu0 = ctypes.c_bool()
        psu1 = ctypes.c_bool()
        
        status = self.rf_psu_dll.COM_HVPSU2D_GetPSUEnable(
            self.port, ctypes.byref(psu0), ctypes.byref(psu1))
        
        return status, psu0.value, psu1.value

    def has_psu_full_range(self):
        """
        Get PSU range-switching implementation.

        Returns
        -------
        tuple
            (status, psu0, psu1).

        """
        psu0 = ctypes.c_bool()
        psu1 = ctypes.c_bool()
        
        status = self.rf_psu_dll.COM_HVPSU2D_HasPSUFullRange(
            self.port, ctypes.byref(psu0), ctypes.byref(psu1))
        
        return status, psu0.value, psu1.value

    def set_psu_full_range(self, psu0, psu1):
        """
        Set PSU full range.

        Parameters
        ----------
        psu0 : bool
            Full range for PSU 0.
        psu1 : bool
            Full range for PSU 1.

        Returns
        -------
        int
            Status code.

        """
        status = self.rf_psu_dll.COM_HVPSU2D_SetPSUFullRange(
            self.port, ctypes.c_bool(psu0), ctypes.c_bool(psu1))
        return status

    def set_psu0_full_range(self, enable):
        """Set PSU0 (positive) full range state."""
        _, _, current_psu1 = self.get_psu_full_range()
        return self.set_psu_full_range(enable, current_psu1)
    
    def set_psu1_full_range(self, enable):
        """Set PSU1 (negative) full range state."""
        _, current_psu0, _ = self.get_psu_full_range()
        return self.set_psu_full_range(current_psu0, enable)

    def get_psu_full_range(self):
        """
        Get PSU full range.

        Returns
        -------
        tuple
            (status, psu0, psu1).

        """
        psu0 = ctypes.c_bool()
        psu1 = ctypes.c_bool()
        
        status = self.rf_psu_dll.COM_HVPSU2D_GetPSUFullRange(
            self.port, ctypes.byref(psu0), ctypes.byref(psu1))
        
        return status, psu0.value, psu1.value

    def get_psu_state(self):
        """
        Get PSU state.

        Returns
        -------
        tuple
            (status, state) where state is a bitmask of ST_* flags.

        """
        state = ctypes.c_uint32()
        status = self.rf_psu_dll.COM_HVPSU2D_GetPSUState(self.port, ctypes.byref(state))
        return status, state.value

    # Configuration Management
    
    def get_device_enable(self):
        """
        Get the enable state of the device.

        Returns
        -------
        tuple
            (status, enable).

        """
        enable = ctypes.c_bool()
        status = self.rf_psu_dll.COM_HVPSU2D_GetDeviceEnable(self.port, ctypes.byref(enable))
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
        status = self.rf_psu_dll.COM_HVPSU2D_SetDeviceEnable(self.port, ctypes.c_bool(enable))
        return status

    def reset_current_config(self):
        """
        Reset current configuration.

        Returns
        -------
        int
            Status code.

        """
        status = self.rf_psu_dll.COM_HVPSU2D_ResetCurrentConfig(self.port)
        return status

    def save_current_config(self, config_number):
        """
        Save current configuration to NVM.

        Parameters
        ----------
        config_number : int
            Configuration number (0-167).

        Returns
        -------
        int
            Status code.

        """
        status = self.rf_psu_dll.COM_HVPSU2D_SaveCurrentConfig(self.port, config_number)
        return status

    def load_current_config(self, config_number):
        """
        Load current configuration from NVM.

        Parameters
        ----------
        config_number : int
            Configuration number (0-167).

        Returns
        -------
        int
            Status code.

        """
        status = self.rf_psu_dll.COM_HVPSU2D_LoadCurrentConfig(self.port, config_number)
        return status

    def get_config_name(self, config_number):
        """
        Get configuration name.

        Parameters
        ----------
        config_number : int
            Configuration number (0-167).

        Returns
        -------
        tuple
            (status, name).

        """
        name = ctypes.create_string_buffer(75)
        status = self.rf_psu_dll.COM_HVPSU2D_GetConfigName(self.port, config_number, name)
        return status, name.value.decode()

    def set_config_name(self, config_number, name):
        """
        Set configuration name.

        Parameters
        ----------
        config_number : int
            Configuration number (0-167).
        name : str
            Configuration name (max 74 characters).

        Returns
        -------
        int
            Status code.

        """
        name_buffer = ctypes.create_string_buffer(name.encode(), 75)
        status = self.rf_psu_dll.COM_HVPSU2D_SetConfigName(self.port, config_number, name_buffer)
        return status

    def get_config_flags(self, config_number):
        """
        Get configuration flags.

        Parameters
        ----------
        config_number : int
            Configuration number (0-167).

        Returns
        -------
        tuple
            (status, active, valid).

        """
        active = ctypes.c_bool()
        valid = ctypes.c_bool()
        
        status = self.rf_psu_dll.COM_HVPSU2D_GetConfigFlags(
            self.port, config_number, ctypes.byref(active), ctypes.byref(valid))
        
        return status, active.value, valid.value

    def set_config_flags(self, config_number, active, valid):
        """
        Set configuration flags.

        Parameters
        ----------
        config_number : int
            Configuration number (0-167).
        active : bool
            Active flag.
        valid : bool
            Valid flag.

        Returns
        -------
        int
            Status code.

        """
        status = self.rf_psu_dll.COM_HVPSU2D_SetConfigFlags(
            self.port, config_number, ctypes.c_bool(active), ctypes.c_bool(valid))
        return status

    def get_config_list(self):
        """
        Get configuration list.

        Returns
        -------
        tuple
            (status, active_list, valid_list) where lists contain 168 boolean values.

        """
        active = (ctypes.c_bool * 168)()
        valid = (ctypes.c_bool * 168)()
        
        status = self.rf_psu_dll.COM_HVPSU2D_GetConfigList(self.port, active, valid)
        return status, [active[i] for i in range(168)], [valid[i] for i in range(168)]

    # System
    
    def restart(self):
        """
        Restart the controller.

        Returns
        -------
        int
            Status code.

        """
        status = self.rf_psu_dll.COM_HVPSU2D_Restart(self.port)
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
        
        status = self.rf_psu_dll.COM_HVPSU2D_GetCPUData(
            self.port, ctypes.byref(load), ctypes.byref(frequency))
        
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
        
        status = self.rf_psu_dll.COM_HVPSU2D_GetUptime(
            self.port, ctypes.byref(seconds), ctypes.byref(milliseconds), ctypes.byref(optime))
        
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
        
        status = self.rf_psu_dll.COM_HVPSU2D_GetTotalTime(
            self.port, ctypes.byref(uptime), ctypes.byref(optime))
        
        return status, uptime.value, optime.value

    def get_hw_type(self):
        """
        Get the hardware type.

        Returns
        -------
        tuple
            (status, hw_type).

        """
        hw_type = ctypes.c_uint32()
        status = self.rf_psu_dll.COM_HVPSU2D_GetHWType(self.port, ctypes.byref(hw_type))
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
        status = self.rf_psu_dll.COM_HVPSU2D_GetHWVersion(self.port, ctypes.byref(hw_version))
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
        status = self.rf_psu_dll.COM_HVPSU2D_GetFWVersion(self.port, ctypes.byref(version))
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
        status = self.rf_psu_dll.COM_HVPSU2D_GetFWDate(self.port, date_string)
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
        status = self.rf_psu_dll.COM_HVPSU2D_GetProductID(self.port, identification)
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
        status = self.rf_psu_dll.COM_HVPSU2D_GetProductNo(self.port, ctypes.byref(number))
        return status, number.value

    # Communication port status
    
    def get_interface_state(self):
        """
        Get software interface state.

        Returns
        -------
        int
            Interface state code.

        """
        state = self.rf_psu_dll.COM_HVPSU2D_GetInterfaceState(self.port)
        return state

    def get_error_message(self):
        """
        Get the error message corresponding to the software interface state.

        Returns
        -------
        str
            Error message.

        """
        self.rf_psu_dll.COM_HVPSU2D_GetErrorMessage.restype = ctypes.c_char_p
        msg_ptr = self.rf_psu_dll.COM_HVPSU2D_GetErrorMessage(self.port)
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
        state = self.rf_psu_dll.COM_HVPSU2D_GetIOState(self.port)
        return state

    def get_io_error_message(self):
        """
        Get the error message corresponding to the serial port interface state.

        Returns
        -------
        str
            Error message.

        """
        self.rf_psu_dll.COM_HVPSU2D_GetIOErrorMessage.restype = ctypes.c_char_p
        msg_ptr = self.rf_psu_dll.COM_HVPSU2D_GetIOErrorMessage(self.port)
        message = msg_ptr.decode() if msg_ptr else "No error"
        return message
