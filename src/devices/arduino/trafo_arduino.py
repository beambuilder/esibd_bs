"""
Trafo-locker Arduino controller.

Reads temperature and fan PWM from the Trafo_Locker Arduino via serial CSV:

    ``18.81,29``

Every 20th line the firmware prints a header — ``parse_data()`` simply
returns None for non-numeric lines, so no separate filtering is needed.
"""

from typing import Any, Dict, Optional

from .arduino import Arduino


class TrafoArduino(Arduino):
    """
    Arduino controller for the trafo-locker cabinet.

    CSV format (500 ms interval):
        Temperature[degC], Fan_PWR[%]

    Example:
        trafo = TrafoArduino("trafo_01", port="COM4")
        trafo.connect()
        trafo.start_housekeeping(interval=1.0)
    """

    # ------------------------------------------------------------------
    #  Parsing
    # ------------------------------------------------------------------

    def parse_data(self, data_line: str) -> Optional[Dict[str, Any]]:
        """
        Parse a trafo-locker CSV line.

        Expected format: ``18.81,29``

        Returns:
            dict with keys *temperature*, *fan_power*, *raw_data*
            — or None on failure.
        """
        try:
            parts = data_line.split(",")
            if len(parts) != 2:
                return None

            temperature = float(parts[0].strip())
            fan_power = int(parts[1].strip())

            return {
                "temperature": temperature,
                "fan_power": fan_power,
                "raw_data": data_line,
            }
        except (ValueError, IndexError):
            self.logger.debug(f"Failed to parse trafo data: {data_line!r}")
            return None

    # ------------------------------------------------------------------
    #  Housekeeping
    # ------------------------------------------------------------------

    def hk_monitor(self) -> None:
        """Read and log trafo-locker sensor data."""
        try:
            rtn = self.read_arduino_data()

            if rtn is not None:
                self.custom_logger(
                    self.device_id, self.port, "Temp", rtn["temperature"], "degC"
                )
                self.custom_logger(
                    self.device_id, self.port, "Fan_PWR", rtn["fan_power"], "%"
                )
            else:
                self.logger.debug("No valid trafo data received.")
        except Exception as e:
            self.logger.error(f"Trafo housekeeping monitoring failed: {e}")
