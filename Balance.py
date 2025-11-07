import time
import serial
import re
import logging
from pathlib import Path
try:
    from .Utils import RETRY_LIMIT
    from .Instrument import Instrument, ConnectionType
    from .Resource import Status
except Exception as e:
    from Utils import RETRY_LIMIT
    from Instrument import Instrument, ConnectionType
    from Resource import Status

class Balance(Instrument):
    """
    Electronic balance controlled over a serial connection.
    Reads weight data until measurement stabilizes.
    """

    def __init__(self, name: str, identifier: int, status, baud_rate: int = 9600, stable_count=15, tolerance=5E-4, **kwargs):
        super().__init__(name=name, connection_type=ConnectionType.SERIAL,
                         identifier=identifier, status=status)
        self.baud_rate = baud_rate
        self.serial = None
        self.stable_count = stable_count
        self.previous_measurement = tolerance

    # ---------- Instrument Lifecycle ----------

    def connect(self):
        """Open serial connection."""
        try:
            self.serial = serial.Serial(self.comm_port, self.baud_rate, timeout=1)
            self.update_status(Status.IN_USE)
            self.log(f"Connected to balance on {self.comm_port} at {self.baud_rate} baud.")
            return
        except Exception as e:
            self.log(f"Failed to connect to {self.comm_port}: {e}",
                        level=logging.ERROR)
            self.update_status(Status.ERROR)
            raise ConnectionError(f"Unable to connect to balance on {self.comm_port} after {RETRY_LIMIT} attempts.")

    def disconnect(self):
        """Close serial connection."""
        if self.serial:
            self.serial.close()
            self.update_status(Status.AVAILABLE)
            self.log(f"Disconnected from balance on {self.comm_port}.")

    # ---------- Measurement Action ----------

    def action(self, period=0.1):
        """
        Perform a mass measurement and wait until the reading stabilizes.
        Returns:
            float: The stabilized mass measurement.
        """
        if not self.serial:
            self.connect()

        # Wait briefly before measurement (allow balance to initialize)
        time.sleep(5)

        stable_count = 0

        while True:
            try:
                line = self.serial.readline().decode(errors="ignore").strip()
                if not line:
                    continue

                match = re.search(r"\d+\.\d+", line)
                if not match:
                    continue

                measurement = float(match.group())
                self.log(f"Received measurement: {measurement}")

                # Stability detection: skip lines with '?' or unstable values
                if '?' not in line:
                    stable_count += 1
                else:
                    stable_count = 0

                if stable_count >= self.stable_count:
                    self.log(f"Measurement stabilized: {measurement}")
                    return measurement

                time.sleep(period)

            except Exception as e:
                self.log(f"Error during measurement: {e}", level=logging.ERROR)
                time.sleep(1)
