import time
import serial
import logging
from pathlib import Path
from enum import Enum, auto

from core.Instrument import Instrument, ConnectionType
from core.Resource import Resource
from core.Register import register_resource

@register_resource("valve")
class Valve(Instrument):
    """
    A serial-controlled valve instrument.
    Subclass of Instrument with actions for switching valve positions.
    """

    def __init__(self, name: str, id, identifier: int, status, baud_rate: int = 9600):
        super().__init__(name=name, id=id, connection_type=ConnectionType.SERIAL,
                         identifier=identifier, status=status)
        self.baud_rate = baud_rate
        self.ser = serial.Serial(self.comm_port, self.baud_rate, timeout=1)
        self._go_to_position(1)
        self.position = 1
        self.ser.close()

    # --------------------------
    # Connection Methods
    # --------------------------
    def create(self):
        """Establish a serial connection to the valve."""
        try:
            self.ser = serial.Serial(self.comm_port, self.baud_rate, timeout=1)
            self.status = Resource.Status.IN_USE
            self.log(f"Connected to valve on {self.comm_port} at {self.baud_rate} baud.")
        except Exception as e:
            self.status = Resource.Status.ERROR
            self.log(f"Failed to connect to valve: {e}", level=logging.ERROR)
            raise

    def delete(self):
        """Safely close the serial connection."""
        if self.ser:
            self.ser.close()
            self.status = Resource.Status.AVAILABLE
            self.log("Valve serial connection closed.")
        else:
            self.log("Disconnect called, but serial port was already closed.")

    # --------------------------
    # Action Method
    # --------------------------
    def update(self, dest: int):
        """
        Move the valve to the desired destination port.
        Retries several times if communication fails.
        """
        if self.status != Resource.Status.IN_USE:
            self.log("Cannot move valve — not connected.", level=logging.ERROR)
            raise ConnectionError("Valve not connected.")

        try:
            current_pos = self._get_current_position()
            if current_pos != dest:
                self._go_to_position(dest)
                self.position = dest
                time.sleep(0.5)
                self.log(f"Valve moved from position {current_pos} to {dest}.")
            else:
                self.log(f"Valve already at position {dest}.")
            return  # success
        except Exception as e:
            self.status = Resource.Status.ERROR
            self.log("Failed to move valve after maximum retries.", level=logging.ERROR)
            raise BufferError("Error occurred while moving valve after retries.")
        
    def read(self):
        result = super().read()
        return result.extend({'position':self._get_current_position()})

    # --------------------------
    # Internal Helper Methods
    # --------------------------
    def _get_current_position(self) -> int:
        """Query the current valve position."""
        command = "CP\r"
        self.ser.write(command.encode())
        r = self.ser.read(5).decode("utf-8").strip()
        if not r.startswith("CP"):
            raise ValueError(f"Unexpected valve response: {r}")
        response = int(r[2:4])
        self.log(f"Current valve position: {response}")
        return response

    def _go_to_position(self, dest: int):
        """Send command to move valve to target position."""
        command = f"GO{dest}\r"
        self.ser.write(command.encode())
        self.log(f"Sent command to move valve to position {dest}.")

    def read(self):
        """Extend base status with valve-specific info."""
        base_status = super().read()
        base_status.update({
            "position": self.position,
        })
        return base_status