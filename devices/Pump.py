import serial
import time
import threading
from enum import Enum, auto
from typing import Any, Dict

from core.Instrument import Instrument, ConnectionType
from core.Resource import Resource
from Utils import RETRY_LIMIT
from core.Register import register_resource


baud_rate_map = {1200: 1, 2400: 2, 4800: 3, 9600: 4, 19200: 5, 38400: 6}


@register_resource("pump")
class Pump(Instrument):
    ADJ = 0.143

    # ================= ENUMS =================
    class PumpMode(Enum):
        SET_ROTATION_SPEED = auto()
        READ_ROTATION_SPEED = auto()
        SET_FLOW_RATE = auto()
        READ_FLOW_RATE = auto()
        FLOW_CALIBRATION = auto()

    class State1(Enum):
        STOP_PUMP = 0
        START_PUMP = 1

    class State2(Enum):
        COUNTER_CLOCKWISE = 1
        CLOCKWISE = 0

    # ================= INIT =================
    def __init__(
        self,
        name: str,
        id,
        identifier: int,
        type_name,
        baud_rate: int = 9600,
    ) -> None:
        super().__init__(
            name=name,
            id=id,
            type_name=type_name,
            connection_type=ConnectionType.SERIAL,
            identifier=identifier,
        )

        self.desired_state["flow_rate"] = 0
        self.baud_rate = baud_rate
        self._lock = threading.Lock()

        try:
            self.serial_conn = serial.Serial(self.comm_port, self.baud_rate, timeout=1)
        except Exception as e:
            print(e)
            self.update_status(Resource.Status.ERROR)

        self.remaining_time = 0
        self._stop_event = threading.Event()
        self._control_thread = threading.Thread(
            target=self._control_loop, daemon=True
        )
        self._control_thread.start()

    # ================= CONNECTION =================
    def create(self) -> None:
        self._connected = True
        self.update_status(Resource.Status.IN_USE)

    def delete(self) -> None:
        self._stop_event.set()
        self._connected = False
        self._send_stop()
        self.update_status(Resource.Status.AVAILABLE)

    # ================= UPDATE =================
    def update(self, flow_rate, volume, direction) -> None:
        with self._lock:
            self.desired_state["direction"] = Pump.State2(direction)

        self.remaining_time = volume / flow_rate * 60

        with self._lock:
            self.desired_state["flow_rate"] = flow_rate

        time.sleep(self.remaining_time)

    # ================= CONTROL LOOP =================
    def _control_loop(self):
        while True:
            if self.desired_state["flow_rate"] > 0:
                now = time.time()

                self.desired_state["state1"] = Pump.State1.START_PUMP
                self.desired_state["finish_time"] = now + self.remaining_time
                self.actual_state["finish_time"] = now + self.remaining_time

                with self._lock:
                    self._send_start(
                        self.desired_state["flow_rate"],
                        self.desired_state["direction"],
                    )

                time.sleep(self.remaining_time - Pump.ADJ)
                with self._lock:
                    self._send_stop()
                    self._send_stop()

                self.desired_state["state1"] = Pump.State1.STOP_PUMP
                self.desired_state["flow_rate"] = 0

    # ================= READ =================
    def read(self) -> Dict[str, Any]:
        with self._lock:
            while True:
                try:
                    rotation_speed_bytes = self._send_command(
                        Pump.PumpMode.READ_ROTATION_SPEED
                    )

                    flow_rate_bytes = [0]
                    while flow_rate_bytes[0] != 11:
                        flow_rate_bytes = list(
                            self._send_command(Pump.PumpMode.READ_FLOW_RATE)
                        )

                    flow_rate_bytes = [255 - i for i in flow_rate_bytes]

                    flow_rate = (
                        flow_rate_bytes[5] * 32768
                        + flow_rate_bytes[6] * 128
                        + flow_rate_bytes[7] / 2
                        if flow_rate_bytes[8] > 0
                        else 0
                    )

                    # ---- State decoding (unchanged logic) ----
                    state1 = Pump.State1(flow_rate_bytes[8] // 2)
                    direction = Pump.State2(flow_rate_bytes[9] // 2)

                    self.actual_state.update(
                        {
                            "status": self.status,
                            "flow_rate": flow_rate / 1e6,
                            "state1": state1,
                            "direction": direction,
                        }
                    )

                    result = super().read()
                    result["state"] = self.actual_state

                    print(result)
                    return result

                except Exception:
                    self.update_status(Resource.Status.ERROR)
                    return {"state": {"status": self.status}}

    # ================= LOW LEVEL =================
    def _send_start(self, flow_rate, direction):
        self._send_command(
            mode=Pump.PumpMode.SET_FLOW_RATE,
            flow_rate=flow_rate,
            direction=direction,
            start=True,
        )

    def _send_stop(self):
        self._send_command(
            mode=Pump.PumpMode.SET_FLOW_RATE,
            flow_rate=0.0,
            start=False,
        )

    def _send_command(
        self,
        mode: PumpMode,
        flow_rate=0,
        direction=State2.CLOCKWISE,
        start=False,
    ):
        if not self.serial_conn or not self.serial_conn.is_open:
            self.create()

        state1 = Pump.State1.START_PUMP if start else Pump.State1.STOP_PUMP

        for _ in range(RETRY_LIMIT):
            try:
                cmd = self._generate_command(
                    mode, state1, direction, flow_rate * 1e6
                )
                self.serial_conn.reset_input_buffer()
                self.serial_conn.write(cmd)

                if mode == Pump.PumpMode.READ_ROTATION_SPEED:
                    return self.serial_conn.read(8)
                elif mode == Pump.PumpMode.READ_FLOW_RATE:
                    return self.serial_conn.read(10)
                return
            except Exception:
                time.sleep(1)

        raise BufferError("Pump command failed")

    # ================= COMMAND BUILDING =================
    def _generate_command(self, mode, state1=None, state2=None, value=None):
        pdu = self._get_pdu(mode)

        if mode == Pump.PumpMode.SET_FLOW_RATE:
            pdu += self._num_to_bytes(value, 4) + [state1.value, state2.value]
        elif mode == Pump.PumpMode.SET_ROTATION_SPEED:
            pdu += self._num_to_bytes(value, 2) + [state1.value, state2.value]

        fcs = self._xor_bytes([self.identifier] + pdu)

        return bytearray([233, self.identifier] + pdu + [fcs])

    def _get_pdu(self, mode):
        if mode == Pump.PumpMode.SET_ROTATION_SPEED:
            return [6, 87, 74]
        if mode == Pump.PumpMode.READ_ROTATION_SPEED:
            return [2, 82, 74]
        if mode == Pump.PumpMode.SET_FLOW_RATE:
            return [8, 87, 76]
        if mode == Pump.PumpMode.READ_FLOW_RATE:
            return [2, 82, 76]
        if mode == Pump.PumpMode.FLOW_CALIBRATION:
            return [8, 87, 73, 68, 13, 0]

    @staticmethod
    def _xor_bytes(values):
        r = 0
        for v in values:
            r ^= int(v) & 0xFF
        return r

    @staticmethod
    def _num_to_bytes(num, length):
        value = int(num)
        out = []
        for _ in range(length):
            out.append(value & 0xFF)
            value //= 256
        return list(reversed(out))