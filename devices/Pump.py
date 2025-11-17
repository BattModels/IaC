import serial
import time
import logging
from enum import Enum, auto
from typing import Any, Dict, Optional

from core.Instrument import Instrument, ConnectionType
from core.Resource import Resource
from Utils import RETRY_LIMIT  # assumes you still have this
from core.Register import register_resource

# ----------------------------
# Pump Protocol Enums
# ----------------------------



baud_rate_map = {1200: 1, 2400: 2, 4800: 3, 9600: 4, 19200: 5, 38400: 6}


# ----------------------------
# Pump Instrument Class
# ----------------------------
@register_resource("pump")
class Pump(Instrument):
    """
    Terraform-compatible pump resource.

    Exposed configuration (desired_state keys):
      * flow_rate: float   (your units; previously used x1e6 in command)
      * volume:    float | None   (total volume to deliver; optional)
      * running:   bool    (True=start, False=stop)
      * direction: 'clockwise' | 'counter_clockwise'

    The Terraform provider can simply push those keys into `desired_state`
    via `create` / `update`, and this driver will handle the low-level
    serial/PDU logic.
    """
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


    class Direction(Enum):
        COUNTER_CLOCKWISE = "counter_clockwise"
        CLOCKWISE = "clockwise"

    def __init__(
        self,
        name: str,
        id,
        identifier: int,
        baud_rate: int = 9600,
        desired_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            name=name,
            id=id,
            connection_type=ConnectionType.SERIAL,
            identifier=identifier,
            desired_state=desired_state,
        )
        self.baud_rate = baud_rate
        self.serial_conn: Optional[serial.Serial] = None

    # =======================================================
    # Instrument template implementations
    # =======================================================

    def create(self) -> None:
        if self.serial_conn and self.serial_conn.is_open:
            self._connected = True
            return

        try:
            self.serial_conn = serial.Serial(self.comm_port, self.baud_rate, timeout=1)
            self._connected = True
            self.update_status(Resource.Status.IN_USE)
            self.log(f"[CONNECT] Pump connected on {self.comm_port}")
        except Exception as exc:
            self._connected = False
            self.update_status(Resource.Status.ERROR)
            self.log(f"[CONNECT] Failed to connect pump: {exc}", logging.ERROR)
            raise

    def delete(self) -> None:
        try:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
            self._connected = False
            self.update_status(Resource.Status.AVAILABLE)
            self.log("[DISCONNECT] Pump disconnected")
        except Exception as exc:
            self.update_status(Resource.Status.ERROR)
            self.log(f"[DISCONNECT] Failed to disconnect pump: {exc}", logging.ERROR)
            raise

    def update(self) -> None:
        """
        Map desired_state dict onto actual pump commands.

        Expected keys:
          * flow_rate (float)
          * volume (float, optional)
          * running (bool)
          * direction ('clockwise' | 'counter_clockwise')
        """
        running = bool(self.desired_state.get("running", False))
        flow_rate = float(self.desired_state.get("flow_rate", 0.0))
        volume = self.desired_state.get("volume")  # may be None
        direction_value = self.desired_state.get("direction", Pump.Direction.CLOCKWISE.value)

        if isinstance(direction_value, Pump.Direction):
            direction = direction_value
        else:
            direction = Pump.Direction(direction_value)

        if not running or flow_rate <= 0.0:
            # Stop the pump
            self._send_command(
                mode=Pump.PumpMode.SET_FLOW_RATE,
                flow_rate=0.0,
                direction=direction,
                start=False,
                volume=None,
            )
            return

        # Run pump: for given volume (finite time) or effectively continuous
        self._send_command(
            mode=Pump.PumpMode.SET_FLOW_RATE,
            flow_rate=flow_rate,
            direction=direction,
            start=True,
            volume=volume,
        )

    def read(self) -> Dict[str, Any]:
        """
        If your device supports readback (READ_FLOW_RATE etc.), you could
        actually query it here. For now we mirror desired_state on success,
        which is still useful from Terraform's POV.
        """
        state = {
            "flow_rate": self.desired_state.get("flow_rate", 0.0),
            "volume": self.desired_state.get("volume"),
            "running": self.desired_state.get("running", False),
            "direction": self.desired_state.get("direction", Pump.Direction.CLOCKWISE.value),
            "status": self.status.name,
        }
        return state

    # =======================================================
    # Low-level command helpers (your original protocol)
    # =======================================================

    def _send_command(
        self,
        mode: PumpMode,
        flow_rate: float,
        direction: Direction,
        start: bool,
        volume: Optional[float] = None,
    ) -> None:
        """Wrapper around retry + PDU logic."""
        if not self.serial_conn or not self.serial_conn.is_open:
            self._connect()

        # Map high-level args to protocol enums
        state1 = Pump.State1.START_PUMP if start else Pump.State1.STOP_PUMP
        state2 = Pump.State2.CLOCKWISE if direction == Pump.Direction.CLOCKWISE else Pump.State2.COUNTER_CLOCKWISE

        rest_time = 0.0
        if volume is not None and flow_rate > 0:
            # Using your previous formula: time [s] = volume / rate * 60
            rest_time = float(volume) / float(flow_rate) * 60.0

        for _ in range(RETRY_LIMIT):
            try:
                start_cmd = self._generate_command(
                    mode=mode,
                    state1=state1,
                    state2=state2,
                    value=flow_rate * 1e6,  # same scaling you used before
                )
                stop_cmd = self._generate_command(
                    mode=mode,
                    state1=Pump.State1.STOP_PUMP,
                    state2=state2,
                    value=0.0,
                )

                self.serial_conn.write(start_cmd)
                if rest_time > 0.0:
                    time.sleep(rest_time)
                    self.serial_conn.write(stop_cmd)

                self.log(
                    f"[COMMAND] mode={mode.name}, flow_rate={flow_rate}, "
                    f"direction={direction.value}, start={start}, volume={volume}"
                )
                return
            except Exception as exc:
                self.update_status(Resource.Status.ERROR)
                self.log(f"[COMMAND] Pump command failed: {exc}", logging.ERROR)
                time.sleep(1.0)

        raise BufferError("Pump command failed after retries")

    def _generate_command(
        self,
        mode: PumpMode,
        state1: State1,
        state2: State2,
        value: float,
    ) -> bytearray:
        pdu = self._get_pdu(mode)
        if mode == Pump.PumpMode.SET_ROTATION_SPEED:
            pdu += self._num_to_bytes(value, 2) + [state1.value, state2.value]
        elif mode == Pump.PumpMode.SET_FLOW_RATE:
            pdu += self._num_to_bytes(value, 4) + [state1.value, state2.value]
        elif mode == Pump.PumpMode.FLOW_CALIBRATION:
            # You can extend this as needed.
            pass

        fcs = self._xor_bytes([self.identifier] + pdu)
        return bytearray([233, self.identifier] + pdu + [fcs])

    def _get_pdu(self, mode: PumpMode) -> list[int]:
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
        return []

    @staticmethod
    def _xor_bytes(values: list[int]) -> int:
        result = 0
        for v in values:
            result ^= int(v) & 0xFF
        return result

    @staticmethod
    def _num_to_bytes(num: float, length: int) -> list[int]:
        """Convert an integer value into a big-endian byte list of given length."""
        value = int(num)
        result: list[int] = []
        for _ in range(length):
            result.append(value & 0xFF)
            value //= 256
        result.reverse()
        return result