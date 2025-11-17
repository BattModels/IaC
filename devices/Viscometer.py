import serial
import time
import logging
import numpy as np
from enum import Enum, auto

from core.Resource import Resource
from core.Instrument import Instrument, ConnectionType


# ----------------------------
# Viscometer Modes
# ----------------------------


# ----------------------------
# Viscometer Class
# ----------------------------
from core.Register import register_resource

@register_resource("viscometer")
class Viscometer(Instrument):
    """
    Viscometer instrument capable of individual or composite actions
    based on ViscometerMode.
    """
    class ViscometerMode(Enum):
        ENABLE = auto()
        ZERO = auto()
        START = auto()
        STOP = auto()
        READ = auto()


    def __init__(self, name: str, id, identifier, status, baud_rate=9600):
        super().__init__(
            name=name,
            id=id,
            connection_type=ConnectionType.SERIAL,
            identifier=identifier,
            status=status
        )
        self.baud_rate = baud_rate
        self.serial_conn = None

    # ----------------------------
    # Connection Handling
    # ----------------------------
    def create(self):
        try:
            self.serial_conn = serial.Serial(f"COM{self.identifier}", self.baud_rate, timeout=1)
            self.update_status(Resource.Status.IN_USE)
            self._send_command(Viscometer.ViscometerMode.ENABLE)
            self.log("Enabled viscometer")
            self.log(f"Connected to viscometer on {self.identifier}")
        except Exception as e:
            self.update_status(Resource.Status.ERROR)
            self.log(f"Failed to connect: {e}", logging.ERROR)
            raise

    def delete(self):
        try:
            if self.serial_conn:
                self.serial_conn.close()
            self.update_status(Resource.Status.AVAILABLE)
            self.log("Disconnected viscometer")
        except Exception as e:
            self.update_status(Resource.Status.ERROR)
            self.log(f"Failed to disconnect: {e}", logging.ERROR)
            raise

    # ----------------------------
    # Action Handling
    # ----------------------------
    def update(self, mode: ViscometerMode, rpm: int = 0, stablization_time: int = 5,
               data_points: int = 10, period: float = 1.0):
        """
        Perform a single or compound viscometer action depending on the mode.
        """
        if self.status != Resource.Status.IN_USE:
            raise RuntimeError("Viscometer must be connected before action")

        try:
            if mode == Viscometer.ViscometerMode.ZERO:
                self._send_command(Viscometer.ViscometerMode.ZERO)
                self.log("Zeroed viscometer")

            else:
                self._send_command(Viscometer.ViscometerMode.START, rpm=rpm)
                self.log(f"Started measurement at {rpm} RPM")
                time.sleep(stablization_time)

                cp_values, temp_values = [], []
                for _ in range(data_points):
                    self._send_command(Viscometer.ViscometerMode.READ)
                    raw_data = self.serial_conn.read(100).decode('utf-8')
                    torque, temp = self._parse_data(raw_data, rpm)
                    cp_values.append(torque)
                    temp_values.append(temp)
                    time.sleep(period)

                cp_mean = np.round(np.mean(cp_values), 4)
                temp_mean = np.round(np.mean(temp_values), 4)
                self.log(f"Measured viscosity {cp_mean} cp, temperature {temp_mean}")
                self._send_command(Viscometer.ViscometerMode.STOP)
                self.log("Stopped viscometer")
                return cp_mean, temp_mean

        except Exception as e:
            self.update_status(Resource.Status.ERROR)
            self.log(f"Viscometer action failed ({mode.name}): {e}", logging.ERROR)
            raise

    # ----------------------------
    # Helper Methods
    # ----------------------------
    def _send_command(self, mode: ViscometerMode, rpm: int = 0):
        cmd = self._generate_command(mode, rpm)
        self.serial_conn.write(cmd.encode('utf-8'))

    @staticmethod
    def _generate_command(mode: ViscometerMode, rpm: int = 0):
        if mode == Viscometer.ViscometerMode.ENABLE:
            return "E\r"
        if mode == Viscometer.ViscometerMode.ZERO:
            return "Z\r"
        if mode == Viscometer.ViscometerMode.START:
            return f"V{format(rpm * 100, '05X')}\r"
        if mode == Viscometer.ViscometerMode.STOP:
            return "V00000\r"
        if mode == Viscometer.ViscometerMode.READ:
            return "R\r"

    @staticmethod
    def _parse_data(data_str: str, rpm: int):
        last_r_index = data_str.rfind('R')
        data_str = data_str[last_r_index + 1:] if last_r_index != -1 else ""
        tor_str = data_str[0:4]
        temp_str = data_str[4:8]
        torque = int(tor_str, 16) / 100 * 6 / rpm
        temp = (int(temp_str, 16) - 4000) / 40
        return torque, temp