"""AMPR (Amplifier) base device class for CGC."""

import ctypes
import json
import os

class AMPRBase:
    """AMPR base device class."""
    
    # Error codes (from COM-AMPR-12.h)
    NO_ERR = 0
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
    
    # Controller status values (from COM-AMPR-12.h)
    MAIN_STATE = {
        0: 'ST_ON',              # PSUs are on
        1: 'ST_OVERLOAD',        # HV PSUs overloaded
        2: 'ST_STBY',            # HV PSUs are stand-by
        0x8000: 'ST_ERROR',      # General error
        0x8001: 'ST_ERR_MODULE', # PSU-module error
        0x8002: 'ST_ERR_VSUP',   # Supply-voltage error
        0x8003: 'ST_ERR_TEMP_LOW', # Low-temperature error
        0x8004: 'ST_ERR_TEMP_HIGH', # Overheating error
        0x8005: 'ST_ERR_ILOCK',   # Interlock error
        0x8006: 'ST_ERR_PSU_DIS', # Error due to disabled PSUs
        0x8007: 'ST_ERR_HV_PSU'   # HV could not reach nominal value
    }
    
    # Device state bits (from COM-AMPR-12.h)
    DEVICE_STATE = {
        (1 << 0x0): 'DS_PSU_ENB',     # PSUs enabled
        (1 << 0x8): 'DS_VOLT_FAIL',   # Supply voltages failure
        (1 << 0x9): 'DS_HV_FAIL',     # High voltages failure
        (1 << 0xA): 'DS_FAN_FAIL',    # Fan failure
        (1 << 0xB): 'DS_ILOCK_FAIL',  # Interlock failure
        (1 << 0xC): 'DS_MODULE_FAIL', # Module configuration failure
        (1 << 0xD): 'DS_RATING_FAIL', # Module rating failure
        (1 << 0xE): 'DS_HV_STOP'      # HV PSUs were turned off
    }
    
    # Voltage state bits (from COM-AMPR-12.h)
    VOLTAGE_STATE = {
        (1 << 0x0): 'VS_3V3_OK',   # +3V3 rail voltage OK
        (1 << 0x1): 'VS_5V0_OK',   # +5V0 rail voltage OK
        (1 << 0x2): 'VS_12V_OK',   # +12V rail voltage OK
        (1 << 0x3): 'VS_LINE_ON',  # Line voltage OK
        (1 << 0x4): 'VS_12VP_OK',  # +12Va rail voltage OK
        (1 << 0x5): 'VS_12VN_OK',  # -12Va rail voltage OK
        (1 << 0x6): 'VS_HVP_OK',   # Positive high voltage OK
        (1 << 0x7): 'VS_HVN_OK',   # Negative high voltage OK
        (1 << 0x8): 'VS_HVP_NZ',   # Positive high voltage non-zero
        (1 << 0x9): 'VS_HVN_NZ',   # Negative high voltage non-zero
        (1 << 0xF): 'VS_ICL_ON'    # ICL active, i.e. shorted
    }
    
    # Temperature state bits (from COM-AMPR-12.h)
    TEMPERATURE_STATE = {
        (1 << 0x0): 'TS_HVPPSU_HIGH',  # +HV PSU overheated
        (1 << 0x1): 'TS_HVNPSU_HIGH',  # -HV PSU overheated
        (1 << 0x2): 'TS_AVPSU_HIGH',   # AV PSU overheated
        (1 << 0x3): 'TS_TADC_HIGH',    # ADC overheated
        (1 << 0x4): 'TS_TCPU_HIGH',    # CPU overheated
        (1 << 0x8): 'TS_HVPPSU_LOW',   # +HV PSU too cold
        (1 << 0x9): 'TS_HVNPSU_LOW',   # -HV PSU too cold
        (1 << 0xA): 'TS_AVPSU_LOW',    # AV PSU too cold
        (1 << 0xB): 'TS_TADC_LOW',     # ADC too cold
        (1 << 0xC): 'TS_TCPU_LOW'      # CPU too cold
    }
    
    # Interlock state bits (from COM-AMPR-12.h)
    INTERLOCK_STATE = {
        (1 << 0x0): 'SI_ILOCK_FRONT_ENB',   # Front interlock enable
        (1 << 0x1): 'SI_ILOCK_REAR_ENB',    # Rear interlock enable
        (1 << 0x2): 'SI_ILOCK_FRONT_INV',   # Front interlock invert
        (1 << 0x3): 'SI_ILOCK_REAR_INV',    # Rear interlock invert
        (1 << 0x8): 'SI_ILOCK_FRONT',       # Front interlock level
        (1 << 0x9): 'SI_ILOCK_REAR',        # Rear interlock level
        (1 << 0xA): 'SI_ILOCK_FRONT_LAST',  # Last front interlock level
        (1 << 0xB): 'SI_ILOCK_REAR_LAST',   # Last rear interlock level
        (1 << 0xF): 'SI_ILOCK_ENB'          # Interlock state
    }
    
    # Module constants
    MODULE_NUM = 12          # Maximum module number
    ADDR_BASE = 0x80        # Base-module address
    ADDR_BROADCAST = 0xFF   # Broadcasting address
    
    # Module presence return values
    MODULE_NOT_FOUND = 0    # No module found
    MODULE_PRESENT = 1      # Module with proper type found
    MODULE_INVALID = 2      # Module found but has invalid type
    
    # Fan constants
    FAN_PWM_MAX = 10000     # Maximum PWM value (100%)
    
    # Device type
    DEVICE_TYPE = 0xA3D8    # Expected device type

    def __init__(self, com, log=None, idn=""):
        """
        Initialization

        Parameters
        ----------
        com : int
            COM Port Hardware Side
        log : logfile, optional
            Logging instance where information is logged
        idn : string, optional
            string to append to class name to distinguish between same devices. The default is empty.

        Returns
        -------
        None.

        """
        
        # Get the directory where this file (ampr_base.py) is located
        self.class_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Importing dll for hardware control - path relative to ampr_base.py
        self.ampr_dll_path = os.path.join(self.class_dir, r"AMPR-12_1_01\x64\COM-AMPR-12.dll")
        self.ampr_dll = ctypes.WinDLL(self.ampr_dll_path)

        # Importing error messages. See AMPR manual - path relative to cgc folder
        self.err_path = os.path.join(os.path.dirname(self.class_dir), "error_codes.json")
        with open(self.err_path, "rb") as f:
            self.err_dict = json.load(f)

        self.com = com
        self.log = log
        self.idn = idn

    def open_port(self, com_number):
        """
        Opening communication link to device

        Parameters
        ----------
        com_number : int
            COM port number.

        Returns
        -------
        int
            Status code.

        """
        status = self.ampr_dll.COM_AMPR_12_Open(ctypes.c_ubyte(com_number))
        return status

    def close_port(self):
        """
        Closing the communication link

        Returns
        -------
        int
            Status code.

        """
        status = self.ampr_dll.COM_AMPR_12_Close()
        return status

    def set_baud_rate(self, baud_rate):
        """
        Set communication speed.

        Parameters
        ----------
        baud_rate : int
            Baud rate (usually set to max: 230400).

        Returns
        -------
        tuple
            (status, actual_baud_rate).

        """
        baud_rate_ref = ctypes.c_uint(baud_rate)
        status = self.ampr_dll.COM_AMPR_12_SetBaudRate(ctypes.byref(baud_rate_ref))
        return status, baud_rate_ref.value

    def purge(self):
        """
        Clear data buffers for the port.

        Returns
        -------
        int
            Status code.

        """
        status = self.ampr_dll.COM_AMPR_12_Purge()
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
        status = self.ampr_dll.COM_AMPR_12_DevicePurge(ctypes.byref(empty))
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
        status = self.ampr_dll.COM_AMPR_12_GetBufferState(ctypes.byref(empty))
        return status, empty.value

    # General device information methods
    
    def get_sw_version(self):
        """
        Get the COM-AMPR-12 software version.

        Returns
        -------
        int
            Software version.

        """
        version = self.ampr_dll.COM_AMPR_12_GetSWVersion()
        return version

    def get_fw_version(self):
        """
        Get the firmware version.

        Returns
        -------
        tuple
            (status, version).

        """
        version = ctypes.c_ushort()
        status = self.ampr_dll.COM_AMPR_12_GetFwVersion(ctypes.byref(version))
        return status, version.value

    def get_fw_date(self):
        """
        Get the firmware date.

        Returns
        -------
        tuple
            (status, date_string).

        """
        date_string = ctypes.create_string_buffer(12)
        status = self.ampr_dll.COM_AMPR_12_GetFwDate(date_string)
        return status, date_string.value.decode()

    def get_product_id(self):
        """
        Get the product identification.

        Returns
        -------
        tuple
            (status, identification).

        """
        identification = ctypes.create_string_buffer(81)
        status = self.ampr_dll.COM_AMPR_12_GetProductID(identification)
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
        status = self.ampr_dll.COM_AMPR_12_GetProductNo(ctypes.byref(number))
        return status, number.value

    def get_manuf_date(self):
        """
        Get the manufacturing date.

        Returns
        -------
        tuple
            (status, year, calendar_week).

        """
        year = ctypes.c_ushort()
        calendar_week = ctypes.c_ushort()
        status = self.ampr_dll.COM_AMPR_12_GetManufDate(ctypes.byref(year), ctypes.byref(calendar_week))
        return status, year.value, calendar_week.value

    def get_device_type(self):
        """
        Get the device type.

        Returns
        -------
        tuple
            (status, device_type).

        """
        device_type = ctypes.c_ushort()
        status = self.ampr_dll.COM_AMPR_12_GetDevType(ctypes.byref(device_type))
        return status, device_type.value

    def get_hw_type(self):
        """
        Get the hardware type.

        Returns
        -------
        tuple
            (status, hw_type).

        """
        hw_type = ctypes.c_uint32()
        status = self.ampr_dll.COM_AMPR_12_GetHwType(ctypes.byref(hw_type))
        return status, hw_type.value

    def get_hw_version(self):
        """
        Get the hardware version.

        Returns
        -------
        tuple
            (status, hw_version).

        """
        hw_version = ctypes.c_ushort()
        status = self.ampr_dll.COM_AMPR_12_GetHwVersion(ctypes.byref(hw_version))
        return status, hw_version.value

    def get_uptime(self):
        """
        Get current and total device uptimes.

        Returns
        -------
        tuple
            (status, sec, millisec, total_sec, total_millisec).

        """
        sec = ctypes.c_uint32()
        millisec = ctypes.c_ushort()
        total_sec = ctypes.c_uint32()
        total_millisec = ctypes.c_ushort()
        
        status = self.ampr_dll.COM_AMPR_12_GetUptime(
            ctypes.byref(sec), ctypes.byref(millisec), 
            ctypes.byref(total_sec), ctypes.byref(total_millisec))
        
        return status, sec.value, millisec.value, total_sec.value, total_millisec.value

    def get_optime(self):
        """
        Get current and total device operation times.

        Returns
        -------
        tuple
            (status, sec, millisec, total_sec, total_millisec).

        """
        sec = ctypes.c_uint32()
        millisec = ctypes.c_ushort()
        total_sec = ctypes.c_uint32()
        total_millisec = ctypes.c_ushort()
        
        status = self.ampr_dll.COM_AMPR_12_GetOptime(
            ctypes.byref(sec), ctypes.byref(millisec), 
            ctypes.byref(total_sec), ctypes.byref(total_millisec))
        
        return status, sec.value, millisec.value, total_sec.value, total_millisec.value

    def get_cpu_data(self):
        """
        Get CPU load (0-1 = 0-100%) and frequency (Hz).

        Returns
        -------
        tuple
            (status, load, frequency).

        """
        load = ctypes.c_double()
        frequency = ctypes.c_double()
        status = self.ampr_dll.COM_AMPR_12_GetCPUdata(ctypes.byref(load), ctypes.byref(frequency))
        return status, load.value, frequency.value

    def get_housekeeping(self):
        """
        Get the housekeeping data.

        Returns
        -------
        tuple
            (status, volt_12v, volt_5v0, volt_3v3, volt_agnd, volt_12vp, volt_12vn,
             volt_hvp, volt_hvn, temp_cpu, temp_adc, temp_av, temp_hvp, temp_hvn, line_freq).

        """
        volt_12v = ctypes.c_double()
        volt_5v0 = ctypes.c_double()
        volt_3v3 = ctypes.c_double()
        volt_agnd = ctypes.c_double()
        volt_12vp = ctypes.c_double()
        volt_12vn = ctypes.c_double()
        volt_hvp = ctypes.c_double()
        volt_hvn = ctypes.c_double()
        temp_cpu = ctypes.c_double()
        temp_adc = ctypes.c_double()
        temp_av = ctypes.c_double()
        temp_hvp = ctypes.c_double()
        temp_hvn = ctypes.c_double()
        line_freq = ctypes.c_double()
        
        status = self.ampr_dll.COM_AMPR_12_GetHousekeeping(
            ctypes.byref(volt_12v), ctypes.byref(volt_5v0), ctypes.byref(volt_3v3),
            ctypes.byref(volt_agnd), ctypes.byref(volt_12vp), ctypes.byref(volt_12vn),
            ctypes.byref(volt_hvp), ctypes.byref(volt_hvn), ctypes.byref(temp_cpu),
            ctypes.byref(temp_adc), ctypes.byref(temp_av), ctypes.byref(temp_hvp),
            ctypes.byref(temp_hvn), ctypes.byref(line_freq))
        
        return (status, volt_12v.value, volt_5v0.value, volt_3v3.value, volt_agnd.value,
                volt_12vp.value, volt_12vn.value, volt_hvp.value, volt_hvn.value,
                temp_cpu.value, temp_adc.value, temp_av.value, temp_hvp.value,
                temp_hvn.value, line_freq.value)

    def restart(self):
        """
        Restart the controller.

        Returns
        -------
        int
            Status code.

        """
        status = self.ampr_dll.COM_AMPR_12_Restart()
        return status

    # AMPR Controller methods
    
    def get_state(self):
        """
        Get device main state.

        Returns
        -------
        tuple
            (status, state_hex, state_name).

        """
        state = ctypes.c_ushort()
        status = self.ampr_dll.COM_AMPR_12_GetState(ctypes.byref(state))
        state_value = state.value
        state_name = self.MAIN_STATE.get(state_value, f'UNKNOWN_STATE_0x{state_value:04X}')
        return status, hex(state_value), state_name

    def get_device_state(self):
        """
        Get device state.

        Returns
        -------
        tuple
            (status, state_hex, state_names).

        """
        device_state = ctypes.c_ushort()
        status = self.ampr_dll.COM_AMPR_12_GetDeviceState(ctypes.byref(device_state))
        state_value = device_state.value
        
        # Check which flags are set
        active_states = []
        if state_value == 0:
            active_states.append('DEVICE_OK')
        else:
            for flag, name in self.DEVICE_STATE.items():
                if state_value & flag:
                    active_states.append(name)
        
        return status, hex(state_value), active_states

    def enable_psu(self, enable):
        """
        Set PSUs-enable bit in device state.

        Parameters
        ----------
        enable : bool
            Enable state.

        Returns
        -------
        tuple
            (status, enable_value).

        """
        enable_ref = ctypes.c_bool(enable)
        status = self.ampr_dll.COM_AMPR_12_EnablePSU(ctypes.byref(enable_ref))
        return status, enable_ref.value

    def get_voltage_state(self):
        """
        Get voltage state.

        Returns
        -------
        tuple
            (status, state_hex, state_names).

        """
        voltage_state = ctypes.c_ushort()
        status = self.ampr_dll.COM_AMPR_12_GetVoltageState(ctypes.byref(voltage_state))
        state_value = voltage_state.value
        
        # Check which flags are set
        active_states = []
        if state_value == 0:
            active_states.append('VOLTAGE_OK')
        else:
            for flag, name in self.VOLTAGE_STATE.items():
                if state_value & flag:
                    active_states.append(name)
        
        return status, hex(state_value), active_states

    def get_temperature_state(self):
        """
        Get temperature state.

        Returns
        -------
        tuple
            (status, state_hex, state_names).

        """
        temperature_state = ctypes.c_ushort()
        status = self.ampr_dll.COM_AMPR_12_GetTemperatureState(ctypes.byref(temperature_state))
        state_value = temperature_state.value
        
        # Check which flags are set
        active_states = []
        if state_value == 0:
            active_states.append('TEMPERATURE_OK')
        else:
            for flag, name in self.TEMPERATURE_STATE.items():
                if state_value & flag:
                    active_states.append(name)
        
        return status, hex(state_value), active_states

    def get_interlock_state(self):
        """
        Get interlock state.

        Returns
        -------
        tuple
            (status, state_hex, state_names).

        """
        interlock_state = ctypes.c_ushort()
        status = self.ampr_dll.COM_AMPR_12_GetInterlockState(ctypes.byref(interlock_state))
        state_value = interlock_state.value
        
        # Check which flags are set
        active_states = []
        for flag, name in self.INTERLOCK_STATE.items():
            if state_value & flag:
                active_states.append(name)
        
        return status, hex(state_value), active_states

    def set_interlock_state(self, interlock_control):
        """
        Set interlock control bits.

        Parameters
        ----------
        interlock_control : int
            Interlock control byte.

        Returns
        -------
        int
            Status code.

        """
        status = self.ampr_dll.COM_AMPR_12_SetInterlockState(ctypes.c_ubyte(interlock_control))
        return status

    def get_inputs(self):
        """
        Get instantaneous device input levels.

        Returns
        -------
        tuple
            (status, interlock_front, interlock_rear, input_sync).

        """
        interlock_front = ctypes.c_bool()
        interlock_rear = ctypes.c_bool()
        input_sync = ctypes.c_bool()
        
        status = self.ampr_dll.COM_AMPR_12_GetInputs(
            ctypes.byref(interlock_front), ctypes.byref(interlock_rear), ctypes.byref(input_sync))
        
        return status, interlock_front.value, interlock_rear.value, input_sync.value

    def get_sync_control(self):
        """
        Get device Sync control.

        Returns
        -------
        tuple
            (status, external, invert, level).

        """
        external = ctypes.c_bool()
        invert = ctypes.c_bool()
        level = ctypes.c_bool()
        
        status = self.ampr_dll.COM_AMPR_12_GetSyncControl(
            ctypes.byref(external), ctypes.byref(invert), ctypes.byref(level))
        
        return status, external.value, invert.value, level.value

    def set_sync_control(self, external, invert, level):
        """
        Set device Sync control.

        Parameters
        ----------
        external : bool
            External sync.
        invert : bool
            Invert sync.
        level : bool
            Sync level.

        Returns
        -------
        int
            Status code.

        """
        status = self.ampr_dll.COM_AMPR_12_SetSyncControl(
            ctypes.c_bool(external), ctypes.c_bool(invert), ctypes.c_bool(level))
        return status

    def get_fan_data(self):
        """
        Get fan data.

        Returns
        -------
        tuple
            (status, failed, max_rpm, set_rpm, measured_rpm, pwm).

        """
        failed = ctypes.c_bool()
        max_rpm = ctypes.c_ushort()
        set_rpm = ctypes.c_ushort()
        measured_rpm = ctypes.c_ushort()
        pwm = ctypes.c_ushort()
        
        status = self.ampr_dll.COM_AMPR_12_GetFanData(
            ctypes.byref(failed), ctypes.byref(max_rpm), ctypes.byref(set_rpm),
            ctypes.byref(measured_rpm), ctypes.byref(pwm))
        
        return status, failed.value, max_rpm.value, set_rpm.value, measured_rpm.value, pwm.value

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
        
        status = self.ampr_dll.COM_AMPR_12_GetLEDData(
            ctypes.byref(red), ctypes.byref(green), ctypes.byref(blue))
        
        return status, red.value, green.value, blue.value

    # Module service methods
    
    def get_module_presence(self):
        """
        Get device's maximum module number & module-presence flags.

        Returns
        -------
        tuple
            (status, valid, max_module, module_presence_list).

        """
        valid = ctypes.c_bool()
        max_module = ctypes.c_uint()
        module_presence = (ctypes.c_ubyte * (self.MODULE_NUM + 1))()
        
        status = self.ampr_dll.COM_AMPR_12_GetModulePresence(
            ctypes.byref(valid), ctypes.byref(max_module), module_presence)
        
        presence_list = [module_presence[i] for i in range(self.MODULE_NUM + 1)]
        return status, valid.value, max_module.value, presence_list

    def update_module_presence(self):
        """
        Update module-presence flags.

        Returns
        -------
        int
            Status code.

        """
        status = self.ampr_dll.COM_AMPR_12_UpdateModulePresence()
        return status

    def rescan_modules(self):
        """
        Rescan address pins of all modules.

        Returns
        -------
        int
            Status code.

        """
        status = self.ampr_dll.COM_AMPR_12_RescanModules()
        return status

    def rescan_module(self, address):
        """
        Rescan address pins of the specified module.

        Parameters
        ----------
        address : int
            Module address.

        Returns
        -------
        int
            Status code.

        """
        status = self.ampr_dll.COM_AMPR_12_RescanModule(ctypes.c_uint(address))
        return status

    def restart_module(self, address):
        """
        Restart the specified module.

        Parameters
        ----------
        address : int
            Module address.

        Returns
        -------
        int
            Status code.

        """
        status = self.ampr_dll.COM_AMPR_12_RestartModule(ctypes.c_uint(address))
        return status

    def get_scanned_module_state(self):
        """
        Get the state of the module scan.

        Returns
        -------
        tuple
            (status, module_mismatch, rating_failure).

        """
        module_mismatch = ctypes.c_bool()
        rating_failure = ctypes.c_bool()
        
        status = self.ampr_dll.COM_AMPR_12_GetScannedModuleState(
            ctypes.byref(module_mismatch), ctypes.byref(rating_failure))
        
        return status, module_mismatch.value, rating_failure.value

    def set_scanned_module_state(self):
        """
        Reset the module mismatch, i.e save the current device configuration.

        Returns
        -------
        int
            Status code.

        """
        status = self.ampr_dll.COM_AMPR_12_SetScannedModuleState()
        return status

    def get_scanned_module_params(self, address):
        """
        Get scanned module parameters.

        Parameters
        ----------
        address : int
            Module address.

        Returns
        -------
        tuple
            (status, scanned_product_no, saved_product_no, scanned_hw_type, saved_hw_type).

        """
        scanned_product_no = ctypes.c_uint32()
        saved_product_no = ctypes.c_uint32()
        scanned_hw_type = ctypes.c_uint32()
        saved_hw_type = ctypes.c_uint32()
        
        status = self.ampr_dll.COM_AMPR_12_GetScannedModuleParams(
            ctypes.c_uint(address), ctypes.byref(scanned_product_no), 
            ctypes.byref(saved_product_no), ctypes.byref(scanned_hw_type), 
            ctypes.byref(saved_hw_type))
        
        return (status, scanned_product_no.value, saved_product_no.value,
                scanned_hw_type.value, saved_hw_type.value)

    def get_module_fw_version(self, address):
        """
        Get the module firmware version.

        Parameters
        ----------
        address : int
            Module address.

        Returns
        -------
        tuple
            (status, fw_version).

        """
        fw_version = ctypes.c_ushort()
        status = self.ampr_dll.COM_AMPR_12_GetModuleFwVersion(
            ctypes.c_uint(address), ctypes.byref(fw_version))
        return status, fw_version.value

    # Additional module methods would be added here based on the full header file
    # These would include voltage setting/getting methods, module housekeeping, etc.
    
    def get_module_product_no(self, address):
        """
        Get the module product number.

        Parameters
        ----------
        address : int
            Module address.

        Returns
        -------
        tuple
            (status, product_no).

        """
        product_no = ctypes.c_uint32()
        status = self.ampr_dll.COM_AMPR_12_GetModuleProductNo(
            ctypes.c_uint(address), ctypes.byref(product_no))
        return status, product_no.value

    def get_module_hw_type(self, address):
        """
        Get the module hardware type.

        Parameters
        ----------
        address : int
            Module address.

        Returns
        -------
        tuple
            (status, hw_type).

        """
        hw_type = ctypes.c_uint32()
        status = self.ampr_dll.COM_AMPR_12_GetModuleHwType(
            ctypes.c_uint(address), ctypes.byref(hw_type))
        return status, hw_type.value

    def get_module_hw_version(self, address):
        """
        Get the module hardware version.

        Parameters
        ----------
        address : int
            Module address.

        Returns
        -------
        tuple
            (status, hw_version).

        """
        hw_version = ctypes.c_ushort()
        status = self.ampr_dll.COM_AMPR_12_GetModuleHwVersion(
            ctypes.c_uint(address), ctypes.byref(hw_version))
        return status, hw_version.value

    def get_module_state(self, address):
        """
        Get the module state.

        Parameters
        ----------
        address : int
            Module address.

        Returns
        -------
        tuple
            (status, state).

        """
        state = ctypes.c_ushort()
        status = self.ampr_dll.COM_AMPR_12_GetModuleState(
            ctypes.c_uint(address), ctypes.byref(state))
        return status, state.value

    def get_module_housekeeping(self, address):
        """
        Get module housekeeping data.

        Parameters
        ----------
        address : int
            Module address.

        Returns
        -------
        tuple
            (status, volt_24vp, volt_24vn, volt_12vp, volt_12vn, volt_5v0, volt_3v3,
             temp_psu, temp_board, volt_ref).

        """
        volt_24vp = ctypes.c_double()
        volt_24vn = ctypes.c_double()
        volt_12vp = ctypes.c_double()
        volt_12vn = ctypes.c_double()
        volt_5v0 = ctypes.c_double()
        volt_3v3 = ctypes.c_double()
        temp_psu = ctypes.c_double()
        temp_board = ctypes.c_double()
        volt_ref = ctypes.c_double()
        
        status = self.ampr_dll.COM_AMPR_12_GetModuleHousekeeping(
            ctypes.c_uint(address), ctypes.byref(volt_24vp), ctypes.byref(volt_24vn),
            ctypes.byref(volt_12vp), ctypes.byref(volt_12vn), ctypes.byref(volt_5v0),
            ctypes.byref(volt_3v3), ctypes.byref(temp_psu), ctypes.byref(temp_board),
            ctypes.byref(volt_ref))
        
        return (status, volt_24vp.value, volt_24vn.value, volt_12vp.value, 
                volt_12vn.value, volt_5v0.value, volt_3v3.value,
                temp_psu.value, temp_board.value, volt_ref.value)

    # Voltage control methods for modules
    
    def set_module_voltage(self, address, channel, voltage):
        """
        Set module output voltage.

        Parameters
        ----------
        address : int
            Module address (0-11).
        channel : int
            Channel number (1-4).
        voltage : float
            Voltage to set.

        Returns
        -------
        int
            Status code.

        """
        status = self.ampr_dll.COM_AMPR_12_SetModuleVoltage(
            ctypes.c_uint(address), ctypes.c_uint(channel), ctypes.c_double(voltage))
        return status

    def get_module_voltage_setpoint(self, address, channel):
        """
        Get module voltage setpoint.

        Parameters
        ----------
        address : int
            Module address (0-11).
        channel : int
            Channel number (1-4).

        Returns
        -------
        tuple
            (status, voltage).

        """
        voltage = ctypes.c_double()
        status = self.ampr_dll.COM_AMPR_12_GetModuleVoltageSetpoint(
            ctypes.c_uint(address), ctypes.c_uint(channel), ctypes.byref(voltage))
        return status, voltage.value

    def get_module_voltage_measured(self, address, channel):
        """
        Get module measured voltage.

        Parameters
        ----------
        address : int
            Module address (0-11).
        channel : int
            Channel number (1-4).

        Returns
        -------
        tuple
            (status, voltage).

        """
        voltage = ctypes.c_double()
        status = self.ampr_dll.COM_AMPR_12_GetModuleVoltageMeasured(
            ctypes.c_uint(address), ctypes.c_uint(channel), ctypes.byref(voltage))
        return status, voltage.value

    # Convenience methods for easier module access
    
    def scan_all_modules(self):
        """
        Scan for all connected modules and return their information.

        Returns
        -------
        dict
            Dictionary with module addresses as keys and module info as values.

        """
        modules = {}
        status, valid, max_module, presence_list = self.get_module_presence()
        
        if status != self.NO_ERR:
            return modules
        
        for addr in range(max_module + 1):
            if presence_list[addr] == self.MODULE_PRESENT:
                module_info = {}
                
                # Get module firmware version
                fw_status, fw_version = self.get_module_fw_version(addr)
                if fw_status == self.NO_ERR:
                    module_info['fw_version'] = fw_version
                
                # Get module product number
                prod_status, product_no = self.get_module_product_no(addr)
                if prod_status == self.NO_ERR:
                    module_info['product_no'] = product_no
                
                # Get module hardware info
                hw_status, hw_type = self.get_module_hw_type(addr)
                if hw_status == self.NO_ERR:
                    module_info['hw_type'] = hw_type
                
                hwv_status, hw_version = self.get_module_hw_version(addr)
                if hwv_status == self.NO_ERR:
                    module_info['hw_version'] = hw_version
                
                # Get module state
                state_status, state = self.get_module_state(addr)
                if state_status == self.NO_ERR:
                    module_info['state'] = state
                
                modules[addr] = module_info
        
        return modules

    def get_all_module_voltages(self, address):
        """
        Get all channel voltages for a specific module.

        Parameters
        ----------
        address : int
            Module address.

        Returns
        -------
        dict
            Dictionary with channel numbers as keys and (setpoint, measured) tuples as values.

        """
        voltages = {}
        
        for channel in range(1, 5):  # Channels 1-4
            # Get setpoint
            set_status, setpoint = self.get_module_voltage_setpoint(address, channel)
            # Get measured value
            meas_status, measured = self.get_module_voltage_measured(address, channel)
            
            if set_status == self.NO_ERR and meas_status == self.NO_ERR:
                voltages[channel] = {
                    'setpoint': setpoint,
                    'measured': measured
                }
            elif set_status == self.NO_ERR:
                voltages[channel] = {
                    'setpoint': setpoint,
                    'measured': None
                }
            elif meas_status == self.NO_ERR:
                voltages[channel] = {
                    'setpoint': None,
                    'measured': measured
                }
        
        return voltages

    def set_all_module_voltages(self, address, voltages):
        """
        Set voltages for all channels of a module.

        Parameters
        ----------
        address : int
            Module address.
        voltages : list or dict
            If list: voltages for channels 1-4
            If dict: {channel: voltage} mapping

        Returns
        -------
        dict
            Dictionary with channel numbers as keys and status codes as values.

        """
        results = {}
        
        if isinstance(voltages, list):
            # List format: [ch1, ch2, ch3, ch4]
            for i, voltage in enumerate(voltages[:4]):  # Max 4 channels
                channel = i + 1
                if voltage is not None:
                    status = self.set_module_voltage(address, channel, voltage)
                    results[channel] = status
        elif isinstance(voltages, dict):
            # Dictionary format: {channel: voltage}
            for channel, voltage in voltages.items():
                if 1 <= channel <= 4 and voltage is not None:
                    status = self.set_module_voltage(address, channel, voltage)
                    results[channel] = status
        
        return results