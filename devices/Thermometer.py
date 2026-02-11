import hid
import time
import logging
from pathlib import Path

from Utils import RETRY_LIMIT
from core.Resource import Resource
from core.Instrument import Instrument, ConnectionType

from core.Register import register_resource

@register_resource("thermometer")
class Thermometer(Instrument):
    """
    HID-based thermometer instrument.
    Provides temperature measurement with retry and logging.
    """

    ADJUSTMENT = -6.1
    

    def __init__(self, name: str, id, identifier: bytes, type_name):
        super().__init__(name=name, id=id, connection_type=ConnectionType.HID, type_name=type_name, identifier=identifier)
        self.device_path = identifier  # HID path string
        self.device = None

    # ----------------------------
    # HID Communication Helpers
    # ----------------------------
    def _open_device(self):
        device = hid.device()
        device.open_path(self.device_path)
        return device

    def _read_record_by_num(self, record_num):
        """Read specific record number."""
        while True:
            try:
                device = self._open_device()
                device.set_nonblocking(True)
                command = [
                    0, 51, 204, 0, 12, 1, 0, 0,
                    record_num // 256, record_num % 256, 0, 1,
                    (13 + record_num // 256 + record_num) % 256
                ]
                device.write(bytes(command))
                result = device.read(20)[12:18]
                temperature = (result[4] * 8 + result[3] // 32) / 10
                device.close()
                return temperature
            except IndexError:
                continue

    def _total_records(self):
        """Fetch total number of stored records."""
        maximum = 0
        for _ in range(5):
            device = self._open_device()
            command = [0, 51, 204, 0, 12, 3, 0, 0, 0, 72, 0, 2, 88]
            device.write(bytes(command))
            result = device.read(14)
            device.close()
            value = result[-3] * 256 + result[-2]
            maximum = max(value, maximum)
        return maximum

    def _is_logging(self):
        """Check if thermometer is actively logging."""
        device = self._open_device()
        for _ in range(2):
            command = [0, 51, 204, 0, 12, 3, 0, 0, 0, 36, 0, 2, 52]
            device.write(bytes(command))
            result = device.read(14)
        device.close()
        return result[-2] == 7

    # ----------------------------
    # Required Methods
    # ----------------------------
    def create(self):
        """Verify HID device connection."""
        try:
            self.device = self._open_device()
            self.status = Resource.Status.IN_USE
            self.log("Thermometer connected successfully.")
        except Exception as e:
            self.status = Resource.Status.ERROR
            self.log(f"Connection failed: {e}", level=logging.ERROR)
            raise

    def delete(self):
        """HID devices disconnect automatically after close()."""
        try:
            self.status = Resource.Status.AVAILABLE
            self.log("Thermometer disconnected.")
        except Exception as e:
            self.status = Resource.Status.ERROR
            self.log(f"Error in measuring temperature.", level=logging.ERROR)
            raise

    def read(self):
        """Perform temperature measurement."""
        result = super().read()
        try:
            if not self._is_logging():
                self.log("Thermometer is not logging", level=logging.ERROR)
                raise BufferError("Thermometer is not logging")

            # Trigger measurement
            device = self._open_device()
            command = [0, 51, 204, 0, 12, 5, 0, 0, 0, 128, 0, 48, 192]
            device.write(bytes(command))
            device.close()

            time.sleep(5)
            num_records = self._total_records()
            self.log(f"Number of records: {num_records}")

            result = self._read_record_by_num(num_records - 2) + self.ADJUSTMENT
            self.log(f"Measured temperature: {result}")
            result.extend({'temperature':result})
            return result

        except Exception as e:
            time.sleep(1)
            raise BufferError("Error in measuring temperature.")
