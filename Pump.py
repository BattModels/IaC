import serial
import time
import array
import logging
from enum import Enum, auto
try:
    from Instrument import *
    from Utils import RETRY_LIMIT, current_dir
except Exception as e:
    from .Instrument import *
    from .Utils import RETRY_LIMIT, current_dir

# ----------------------------
# Pump Modes
# ----------------------------
class PumpMode(Enum):
    SET_ROTATION_SPEED = auto()
    READ_ROTATION_SPEED = auto()
    SET_FLOW_RATE = auto()
    READ_FLOW_RATE = auto()
    FLOW_CALIBRATION = auto()

class State1(Enum):
    STOP_PUMP = 0
    START_PUMP = 1
    PRIME_PUMP = 17

class State2(Enum):
    COUNTER_CLOCKWISE = 1
    CLOCKWISE = 0

baud_rate_map = {1200:1, 2400:2, 4800:3, 9600:4, 19200:5, 38400:6}

# ----------------------------
# Pump Instrument Class
# ----------------------------
class Pump(Instrument):
    def __init__(self, name: str, identifier, status, baud_rate: int = 9600):
        super().__init__(name=name, connection_type=ConnectionType.SERIAL, identifier=identifier, status=status)
        self.baud_rate = baud_rate
        self.serial_conn = None

    # ----------------------------
    # Lifecycle Methods
    # ----------------------------
    def connect(self):
        try:
            self.serial_conn = serial.Serial(f"COM{self.identifier}", self.baud_rate, timeout=1)
            self.update_status(Status.IN_USE)
            self.log(f"Pump connected on {self.identifier}")
        except Exception as e:
            self.update_status(Status.ERROR)
            self.log(f"Failed to connect pump: {e}", logging.ERROR)
            raise

    def disconnect(self):
        try:
            if self.serial_conn:
                self.serial_conn.close()
            self.update_status(Status.AVAILABLE)
            self.log(f"Pump disconnected")
        except Exception as e:
            self.update_status(Status.ERROR)
            self.log(f"Failed to disconnect pump: {e}", logging.ERROR)
            raise

    # ----------------------------
    # Pump Actions
    # ----------------------------
    def action(self, mode: PumpMode, state2: State2, rate, volume):
        """Send a command to the pump with retries"""
        for _ in range(RETRY_LIMIT):
            try:
                start_cmd = self._generate_command(mode, State1.START_PUMP, state2, rate * 1E6)
                rest_time = volume / rate * 60
                if not self.serial_conn:
                    self.connect()
                stop_cmd = self._generate_command(mode, State1.STOP_PUMP, state2, 0)
                self.serial_conn.write(start_cmd)
                time.sleep(rest_time)
                self.serial_conn.write(stop_cmd)
                return
            except Exception as e:
                self.update_status(Status.ERROR)
                self.log(f"Pump action failed: {e}", logging.ERROR)
                time.sleep(1)
        raise BufferError("Pump action failed after retries")

    # ----------------------------
    # Command Generation
    # ----------------------------
    def _generate_command(self, mode: PumpMode, state1: State1, state2: State2, value: float):
        pdu = self._get_pdu(mode)
        if mode == PumpMode.SET_ROTATION_SPEED:
            pdu += self._num_to_bytes(value, 2) + [state1.value, state2.value]
        elif mode == PumpMode.SET_FLOW_RATE:
            pdu += self._num_to_bytes(value, 4) + [state1.value, state2.value]
        # FLOW_CALIBRATION or others could be extended here
        fcs = self._xor_bytes([self.identifier] + pdu)
        return bytearray([233, self.identifier] + pdu + [fcs])

    def _get_pdu(self, mode: PumpMode):
        if mode == PumpMode.SET_ROTATION_SPEED: return [6, 87, 74]
        if mode == PumpMode.READ_ROTATION_SPEED: return [2, 82, 74]
        if mode == PumpMode.SET_FLOW_RATE: return [8, 87, 76]
        if mode == PumpMode.READ_FLOW_RATE: return [2, 82, 76]
        if mode == PumpMode.FLOW_CALIBRATION: return [8, 87, 73, 68, 13, 0]
        return []

    def _xor_bytes(self, int_list):
        result = 0
        for num in int_list:
            result ^= int(num) & 0xFF
        return result

    def _num_to_bytes(self, num, n):
        result = []
        for _ in range(n):
            result.append(int(num) % 256)
            num //= 256
        result.reverse()
        return result


    # ----------------------------
    # Convenience Methods
    # ----------------------------
    def stop(self):
        self.action(PumpMode.SET_FLOW_RATE, State1.STOP_PUMP, State2.CLOCKWISE, 0)
        self.log("Pump stopped")

    def start(self, flow_rate: float, state1=State1.START_PUMP, state2=State2.CLOCKWISE):
        self.action(PumpMode.SET_FLOW_RATE, state1, state2, flow_rate)
        self.log(f"Pump started with flow rate {flow_rate}")
