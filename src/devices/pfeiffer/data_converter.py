"""
Pfeiffer data type converter.

This module provides the PfeifferDataConverter class for converting between
Python data types and Pfeiffer vacuum device protocol data formats.
"""
import math


class PfeifferDataConverter:
    """
    Converter class for Pfeiffer vacuum device datatypes.
    Based on Pfeiffer Vacuum Protocol for RS-485 interface.
    """
    
    # Type 0: boolean_old
    def bool_2_boolean_old(self, val: bool) -> str:
        """
        Convert boolean to Pfeiffer's old boolean format.
        
        Args:
            val: Boolean value to convert.
            
        Returns:
            str: "111111" for True, "000000" for False.
        """
        return "111111" if val else "000000"

    def boolean_old_2_bool(self, val: str) -> bool:
        """
        Convert Pfeiffer's old boolean format to Python boolean.
        
        Args:
            val: String value ("111111" or "000000").
            
        Returns:
            bool: True for "111111", False for "000000".
            
        Raises:
            ValueError: If val is not a valid boolean_old format.
        """
        if val == "111111":
            return True
        elif val == "000000":
            return False
        else:
            raise ValueError(f"Invalid boolean_old format: {val}")

    # Type 1: u_integer
    def int_2_u_integer(self, val: int) -> str:
        """
        Convert integer to Pfeiffer's u_integer format.
        
        Args:
            val: Integer value (0-999999).
            
        Returns:
            str: 6-digit zero-padded string.
            
        Raises:
            ValueError: If val is outside valid range.
        """
        if not (0 <= val <= 999999):
            raise ValueError(f"u_integer value {val} outside range 0-999999")
        return f"{val:06d}"

    def u_integer_2_int(self, val: str) -> int:
        """
        Convert Pfeiffer's u_integer format to Python integer.
        
        Args:
            val: 6-digit string representation.
            
        Returns:
            int: Converted integer value.
        """
        return int(val)

    # Type 2: u_real
    def float_2_u_real(self, val: float) -> str:
        """
        Convert float to Pfeiffer's u_real string format.
        
        Args:
            val: Float value to convert.
            
        Returns:
            str: 6-digit string representation (value * 100).
        """
        u_real = round(val * 100)
        return f"{u_real:06d}"

    def u_real_2_float(self, val: str) -> float:
        """
        Convert Pfeiffer's u_real string format to float.
        
        Args:
            val: String representation to convert.
            
        Returns:
            float: Converted value (string value / 100).
        """
        return int(val) / 100

    # Type 4: string
    def str_2_string(self, val: str) -> str:
        """
        Convert string to Pfeiffer's string format (6 characters).
        
        Args:
            val: String value to convert.
            
        Returns:
            str: 6-character string (padded with spaces or truncated).
        """
        # Ensure only ASCII characters 32-127
        filtered_val = ''.join(c for c in val if 32 <= ord(c) <= 127)
        return filtered_val.ljust(6)[:6]  # Pad with spaces or truncate

    def string_2_str(self, val: str) -> str:
        """
        Convert Pfeiffer's string format to Python string.
        
        Args:
            val: 6-character string from device.
            
        Returns:
            str: String with trailing spaces removed.
        """
        return val.rstrip()

    # Type 6: boolean_new
    def bool_2_boolean_new(self, val: bool) -> str:
        """
        Convert boolean to Pfeiffer's new boolean format.
        
        Args:
            val: Boolean value to convert.
            
        Returns:
            str: "1" for True, "0" for False.
        """
        return "1" if val else "0"

    def boolean_new_2_bool(self, val: str) -> bool:
        """
        Convert Pfeiffer's new boolean format to Python boolean.
        
        Args:
            val: String value ("1" or "0").
            
        Returns:
            bool: True for "1", False for "0".
            
        Raises:
            ValueError: If val is not a valid boolean_new format.
        """
        if val == "1":
            return True
        elif val == "0":
            return False
        else:
            raise ValueError(f"Invalid boolean_new format: {val}")

    # Type 7: u_short_int
    def int_2_u_short_int(self, val: int) -> str:
        """
        Convert integer to Pfeiffer's u_short_int format.
        
        Args:
            val: Integer value (0-999).
            
        Returns:
            str: 3-digit zero-padded string.
            
        Raises:
            ValueError: If val is outside valid range.
        """
        if not (0 <= val <= 999):
            raise ValueError(f"u_short_int value {val} outside range 0-999")
        return f"{val:03d}"

    def u_short_int_2_int(self, val: str) -> int:
        """
        Convert Pfeiffer's u_short_int format to Python integer.
        
        Args:
            val: 3-digit string representation.
            
        Returns:
            int: Converted integer value.
        """
        return int(val)

    # Type 10: u_expo_new
    def float_2_u_expo_new(self, val: float) -> str:
        """
        Convert float to Pfeiffer's u_expo_new format.
        
        Args:
            val: Float value to convert.
            
        Returns:
            str: 6-digit string with mantissa and exponent (exponent - 20).
            
        Example:
            1000.0 -> "100023" (1.0 * 10^3, exponent 3+20=23)
            0.01 -> "100018" (1.0 * 10^-2, exponent -2+20=18)
        """
        if val == 0:
            return "100000"  # 1.0 * 10^-20
        
        # Convert to scientific notation
        exponent = math.floor(math.log10(abs(val)))
        mantissa = val / (10 ** exponent)
        
        # Round mantissa to 4 decimal places and convert to integer representation
        mantissa_int = round(mantissa * 1000)
        
        # Adjust if rounding pushed mantissa >= 10000
        if mantissa_int >= 10000:
            mantissa_int = 1000
            exponent += 1
        
        # Pfeiffer format: exponent with offset of 20
        pfeiffer_exponent = exponent + 20
        
        # Ensure exponent is in valid range (00-99)
        pfeiffer_exponent = max(0, min(99, pfeiffer_exponent))
        
        return f"{mantissa_int:04d}{pfeiffer_exponent:02d}"

    def u_expo_new_2_float(self, val: str) -> float:
        """
        Convert Pfeiffer's u_expo_new format to Python float.
        
        Args:
            val: 6-digit string representation.
            
        Returns:
            float: Converted float value.
            
        Example:
            "100023" -> 1000.0 (1.0 * 10^3)
            "100000" -> 1e-20 (1.0 * 10^-20)
        """
        mantissa_str = val[:4]
        exponent_str = val[4:6]
        
        mantissa = int(mantissa_str) / 1000.0
        exponent = int(exponent_str) - 20
        
        return mantissa * (10 ** exponent)

    # Type 11: string16
    def str_2_string16(self, val: str) -> str:
        """
        Convert string to Pfeiffer's string16 format (16 characters).
        
        Args:
            val: String value to convert.
            
        Returns:
            str: 16-character string (padded with spaces or truncated).
        """
        # Ensure only ASCII characters 32-127
        filtered_val = ''.join(c for c in val if 32 <= ord(c) <= 127)
        return filtered_val.ljust(16)[:16]  # Pad with spaces or truncate

    def string16_2_str(self, val: str) -> str:
        """
        Convert Pfeiffer's string16 format to Python string.
        
        Args:
            val: 16-character string from device.
            
        Returns:
            str: String with trailing spaces removed.
        """
        return val.rstrip()

    # Type 12: string8
    def str_2_string8(self, val: str) -> str:
        """
        Convert string to Pfeiffer's string8 format (8 characters).
        
        Args:
            val: String value to convert.
            
        Returns:
            str: 8-character string (padded with spaces or truncated).
        """
        # Ensure only ASCII characters 32-127
        filtered_val = ''.join(c for c in val if 32 <= ord(c) <= 127)
        return filtered_val.ljust(8)[:8]  # Pad with spaces or truncate

    def string8_2_str(self, val: str) -> str:
        """
        Convert Pfeiffer's string8 format to Python string.
        
        Args:
            val: 8-character string from device.
            
        Returns:
            str: String with trailing spaces removed.
        """
        return val.rstrip()
