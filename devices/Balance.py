import time
import serial
import re
import logging
from typing import Any, Dict

from Utils import RETRY_LIMIT
from core.Instrument import Instrument, ConnectionType
from core.Resource import Resource
from core.Register import register_resource


@register_resource("balance")
class Balance(Instrument):
    """
    Electronic balance over serial.

    Logical state:
        - status

    Observable state:
        - mass_reading
        - is_stable
    """

    def __init__(
        self,
        name: str,
        id,
        identifier: int,
        type_name,
        baud_rate: int = 9600,
        stable_count: int = 10,
        **kwargs,
    ):
        super().__init__(
            name=name,
            id=id,
            type_name=type_name,
            connection_type=ConnectionType.SERIAL,
            identifier=identifier,
        )

        self.baud_rate = baud_rate
        self.stable_count_required = stable_count
        self.serial_conn = None

        # Observable state
        self.actual_state.update({
            "mass_reading": 0.0,
            "is_stable": False,
        })

        # Physical connection established at initialization
        self._connect_serial()

    # ================= Physical Connection =================

    def _connect_serial(self):
        try:
            self.serial_conn = serial.Serial(
                self.comm_port,
                self.baud_rate,
                timeout=1,
            )
            self._connected = True
            self.update_status(Resource.Status.AVAILABLE)
        except Exception as e:
            self._connected = False
            self.update_status(Resource.Status.ERROR)
            self.log(f"Balance connection failed: {e}", level=logging.ERROR)

    # ================= Lifecycle (Logical Only) =================

    def create(self):
        """
        Logical allocation only.
        """
        if self.status != Resource.Status.ERROR:
            self.update_status(Resource.Status.IN_USE)

    def delete(self):
        """
        Logical release only.
        """
        if self.status != Resource.Status.ERROR:
            self.update_status(Resource.Status.AVAILABLE)

    # ================= Read (Observable) =================

    def read(self, period: float = 0.1) -> Dict[str, Any]:
        """
        Continuously reads balance output and updates:
            - mass_reading
            - is_stable
        Stability determined by absence of '?'.
        """

        if not self.serial_conn or not self.serial_conn.is_open:
            self.update_status(Resource.Status.ERROR)
            return super().read()

        stable_counter = 0
        latest_value = self.actual_state.get("mass_reading", 0.0)

        for _ in range(RETRY_LIMIT * 50):
            try:
                line = self.serial_conn.readline().decode(
                    errors="ignore"
                ).strip()

                if not line:
                    continue

                match = re.search(r"\d+\.\d+", line)
                if not match:
                    continue

                latest_value = float(match.group())

                if '?' not in line:
                    stable_counter += 1
                else:
                    stable_counter = 0

                is_stable = stable_counter >= self.stable_count_required

                self.actual_state["status"] = self.status,

                if is_stable:
                    break

                time.sleep(period)

            except Exception as e:
                self.log(f"Read error: {e}", level=logging.ERROR)
                self.update_status(Resource.Status.ERROR)
                return {"state": {"status": self.status}}

        result = super().read()
        result["state"] = {
                    "status": self.status,
                    "mass_reading": latest_value,
                    "is_stable": is_stable,
                }
        return result
