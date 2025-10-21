"""PSU (Power Supply Unit) device class for CGC."""

import ctypes
import json

class PSU:
    """PSU device class."""

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
        
        # Importing dll for hardware control
        self.psu_dll_path = (r"PSU-CTRL-2D_1-01\x64\COM-HVPSU2D.dll")
        self.rf_psu_dll = ctypes.WinDLL(self.psu_dll_path)

        #Importing error messages. See PSU manual.
        self.err_path = r"Add_Ons\json_res\error_codes.json"
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
        com : TYPE
            com port.
        port : TYPE
            port number.
        Returns
        -------
        None.

        """
            
        status = self.rf_psu_dll.COM_HVPSU2D_Open(port, com)
        
        if status == 0:
            print(f"Port {self.port} + Com {self.com} opened")
        elif status != 0:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")


    def close_port(self):
        """
        closing the communication link

        Parameters
        ----------
        logg : TYPE, optional
            Wether to write to log file or not. The default is = True.

        Returns
        -------
        None.

        """
        
        status = self.rf_psu_dll.COM_HVPSU2D_Close(self.port)

        if status == 0:
            print(f"Port {self.port} + Com {self.com} closed")
        elif status != 0:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")

    def set_comspeed(self, baudrate):
        """
        set communication speed. usually set to max: 230400

        Parameters
        ----------
        baudrate : int.

        Returns
        -------
        None.

        """
        
        comspeed = ctypes.c_uint32(baudrate)
        
        status = self.rf_psu_dll.COM_HVPSU2D_SetBaudRate(self.port, ctypes.byref(comspeed))
        
        if status == 0:
            print(f"Communication Speed set to {baudrate} baud")
        else:
            print(f"{self.err_dict[str(status)]}. Check Manual")

    def purge(self):
        """
        Clear data buffers for the port.

        Returns
        -------
        int
            Status code.

        """
        status = self.rf_psu_dll.COM_HVPSU2D_Purge(self.port)
        
        if status == 0:
            print(f"Port {self.port} purged")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Device buffer purged. Empty: {empty.value}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Buffer empty: {empty.value}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Interlock set - Output: {con_out}, BNC: {con_bnc}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Interlock - Output: {con_out.value}, BNC: {con_bnc.value}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
        return status, con_out.value, con_bnc.value

    def get_main_state(self):
        """
        Get the main device status.

        Returns
        -------
        tuple
            (status, state) where state is one of the COM_HVPSU2D_STATE_* constants.

        """
        state = ctypes.c_uint16()
        status = self.rf_psu_dll.COM_HVPSU2D_GetMainState(self.port, ctypes.byref(state))
        
        if status == 0:
            print(f"Main state: 0x{state.value:04X}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
        return status, state.value

    def get_device_state(self):
        """
        Get the device status.

        Returns
        -------
        tuple
            (status, device_state) where device_state is a bitmask of COM_HVPSU2D_DEVST_* flags.

        """
        device_state = ctypes.c_uint32()
        status = self.rf_psu_dll.COM_HVPSU2D_GetDeviceState(self.port, ctypes.byref(device_state))
        
        if status == 0:
            print(f"Device state: 0x{device_state.value:08X}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Housekeeping - VRect: {volt_rect.value}V, V5V0: {volt_5v0.value}V, "
                  f"V3V3: {volt_3v3.value}V, TempCPU: {temp_cpu.value}°C")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Sensor temps - Neg: {temps[0]}°C, Mid: {temps[1]}°C, Pos: {temps[2]}°C")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Fan data retrieved")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"LED - Red: {red.value}, Green: {green.value}, Blue: {blue.value}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"ADC Housekeeping PSU{psu_num} - AVDD: {volt_avdd.value}V, "
                  f"DVDD: {volt_dvdd.value}V, TempADC: {temp_adc.value}°C")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
        return (status, volt_avdd.value, volt_dvdd.value, volt_aldo.value,
                volt_dldo.value, volt_ref.value, temp_adc.value)

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
        
        if status == 0:
            print(f"PSU{psu_num} Housekeeping - 24Vp: {volt_24vp.value}V, "
                  f"12Vp: {volt_12vp.value}V, 12Vn: {volt_12vn.value}V")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
        return status, volt_24vp.value, volt_12vp.value, volt_12vn.value, volt_ref.value

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
        
        if status == 0:
            print(f"PSU{psu_num} Data - Voltage: {voltage.value}V, "
                  f"Current: {current.value}A, Dropout: {volt_dropout.value}V")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
        return status, voltage.value, current.value, volt_dropout.value

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
        
        if status == 0:
            print(f"PSU{psu_num} output voltage set to {voltage}V")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
        return status

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
        
        if status == 0:
            print(f"PSU{psu_num} output voltage: {voltage.value}V")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
        return status, voltage.value

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
        
        if status == 0:
            print(f"PSU{psu_num} set voltage: {voltage_set.value}V, limit: {voltage_limit.value}V")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
        return status, voltage_set.value, voltage_limit.value

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
        
        if status == 0:
            print(f"PSU{psu_num} output current set to {current}A")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
        return status

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
        
        if status == 0:
            print(f"PSU{psu_num} output current: {current.value}A")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
        return status, current.value

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
        
        if status == 0:
            print(f"PSU{psu_num} set current: {current_set.value}A, limit: {current_limit.value}A")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
        return status, current_set.value, current_limit.value

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
        
        if status == 0:
            print(f"PSU enable - PSU0: {psu0}, PSU1: {psu1}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
        return status

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
        
        if status == 0:
            print(f"PSU enable - PSU0: {psu0.value}, PSU1: {psu1.value}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"PSU has full range - PSU0: {psu0.value}, PSU1: {psu1.value}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"PSU full range - PSU0: {psu0}, PSU1: {psu1}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
        return status

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
        
        if status == 0:
            print(f"PSU full range - PSU0: {psu0.value}, PSU1: {psu1.value}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
        return status, psu0.value, psu1.value

    def get_psu_state(self):
        """
        Get PSU state.

        Returns
        -------
        tuple
            (status, state) where state is a bitmask of COM_HVPSU2D_ST_* flags.

        """
        state = ctypes.c_uint32()
        status = self.rf_psu_dll.COM_HVPSU2D_GetPSUState(self.port, ctypes.byref(state))
        
        if status == 0:
            print(f"PSU state: 0x{state.value:08X}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Device enable: {enable.value}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Device enable set to: {enable}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print("Current configuration reset")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Configuration {config_number} saved")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Configuration {config_number} loaded")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Config {config_number} name: {name.value.decode()}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Config {config_number} name set to: {name}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Config {config_number} - Active: {active.value}, Valid: {valid.value}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Config {config_number} flags set - Active: {active}, Valid: {valid}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print("Configuration list retrieved")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print("Controller restarting")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"CPU - Load: {load.value*100:.1f}%, Frequency: {frequency.value/1e6:.1f}MHz")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Uptime: {seconds.value}s, Optime: {optime.value}s")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Total - Uptime: {uptime.value}s, Optime: {optime.value}s")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Hardware type: 0x{hw_type.value:08X}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Hardware version: {hw_version.value}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Firmware version: {version.value}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Firmware date: {date_string.value.decode()}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Product ID: {identification.value.decode()}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        
        if status == 0:
            print(f"Product number: {number.value}")
        else:
            print(f"{self.err_dict[str(status)]}. Check PSU Manual")
        
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
        print(f"Interface state: {state}")
        return state

    def get_error_message(self):
        """
        Get the error message corresponding to the software interface state.

        Returns
        -------
        str
            Error message.

        """
        msg_ptr = self.rf_psu_dll.COM_HVPSU2D_GetErrorMessage(self.port)
        self.rf_psu_dll.COM_HVPSU2D_GetErrorMessage.restype = ctypes.c_char_p
        message = msg_ptr.decode() if msg_ptr else "No error"
        print(f"Error message: {message}")
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
        print(f"IO state: {state}")
        return state

    def get_io_error_message(self):
        """
        Get the error message corresponding to the serial port interface state.

        Returns
        -------
        str
            Error message.

        """
        msg_ptr = self.rf_psu_dll.COM_HVPSU2D_GetIOErrorMessage(self.port)
        self.rf_psu_dll.COM_HVPSU2D_GetIOErrorMessage.restype = ctypes.c_char_p
        message = msg_ptr.decode() if msg_ptr else "No error"
        print(f"IO error message: {message}")
        return message

