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
            #self.logger.debug(f"Failed to parse pump data: {data_line!r}")
            return None

    # ------------------------------------------------------------------
    #  Housekeeping
    # ------------------------------------------------------------------

    def hk_monitor(self) -> None:
        """Read and log pump-locker sensor data."""
        try:
            rtn = self.read_arduino_data()

            if rtn is not None:
                self.custom_logger(
                    self.device_id, self.port, "Temp", rtn["temperature"], "degC"
                )
                self.custom_logger(
                    self.device_id, self.port, "Fan_PWR", rtn["fan_power"], "%"
                )
                self.custom_logger(
                    self.device_id, self.port, "Flow1", rtn["flow_rate_1"], "L/min"
                )
                self.custom_logger(
                    self.device_id, self.port, "Flow2", rtn["flow_rate_2"], "L/min"
                )
            else:
                self.logger.debug("No valid pump data received.")
        except Exception as e:
            self.logger.error(f"Pump housekeeping monitoring failed: {e}")
