import hid
import logging
from time import sleep
from enum import Enum
from pathlib import Path

from core.Instrument import Instrument, ConnectionType
from core.Resource import Resource
from Utils import RETRY_LIMIT


# ----------------------------
# Relay State Enum
# ----------------------------



# ----------------------------
# Relay Instrument Class
# ----------------------------
from core.Register import register_resource

@register_resource("relay")
class Relay(Instrument):
    """
    HID-controlled relay instrument.
    Allows turning specific relay channels ON/OFF.
    """
    class State_Relay(Enum):
        OFF = 0
        ON = 1

    def __init__(self, name: str, id, identifier: bytes, status, num_channels=8):
        """
        Args:
            name (str): Relay device name
            identifier (bytes): HID path (as bytes)
        """
        
        super().__init__(
            name=name,
            id=id,
            connection_type=ConnectionType.HID,
            identifier=identifier,
            status=status,
        )
        self.channel_state = [Relay.State_Relay.OFF for _ in range(num_channels)]
        self.device = hid.device()
        self.device.open_path(self.identifier)
        for i in range(1, num_channels + 1):
            cmd = [0x00, 0xFD, i]
            self.device.send_feature_report(cmd)
        self.device.close()

    # ---------- Connection ----------
    def create(self):
        """Establish HID connection to the relay device."""
        try:
            self.device = hid.device()
            self.device.open_path(self.identifier)
            self.status = Resource.Status.IN_USE
            if self.device.get_product_string() != 'USBRelay8':
                raise ConnectionError("Failed to connect to HID relay.")
            self.log(f"Relay connected via HID: {self.identifier}")
            return
        except Exception as e:
            self.status = Resource.Status.ERROR
            raise ConnectionError("Failed to connect to HID relay.")

    def delete(self):
        """Safely close HID connection."""
        try:
            if self.device:
                self.device.close()
                self.log("Relay HID connection closed.")
            self.status = Resource.Status.AVAILABLE
        except Exception as e:
            self.status = Resource.Status.ERROR
            self.log(f"Error during disconnect: {e}", level=logging.ERROR)

    def read(self):
        """Return relay status, including per-channel ON/OFF states."""
        base_status = super().read()
        base_status.update({f"channel {i + 1}": self.channel_state[i].name for i in range(len(self.channel_state))})
        return base_status

    # ---------- Action ----------
    def update(self, relay_num: int, state: State_Relay):
        """
        Turn a specific relay channel ON or OFF.

        Args:
            relay_num (int): Relay number (1-8)
            state (State3Way): Desired state (ON/OFF)
        """
        if self.status != Resource.Status.IN_USE:
            self.create()

        try:
            if not (1 <= relay_num <= 8):
                raise ValueError("Relay number must be between 1 and 8.")

            cmd = [0x00, 0xFF if state == Relay.State_Relay.ON else 0xFD, relay_num]
            self.device.send_feature_report(cmd)
            self.channel_state[relay_num - 1] = state
            self.log(f"Relay {relay_num} -> {state.name} (Command: {cmd})")

            sleep(0.05)
        except Exception as e:
            self.status = Resource.Status.ERROR
            self.log(f"Failed to set relay {relay_num}: {e}", level=logging.ERROR)
            raise BufferError(f"Failed to toggle relay {relay_num}") from e


# ----------------------------
# Example usage
# ----------------------------
if __name__ == "__main__":
    PATH = b'\\\\?\\HID#VID_16C0&PID_05DF#8&d39fb6d&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}'
    relay = Relay(name="Relay", identifier=PATH)
    relay.connect()

    relay.action(1, Relay.State_Relay.ON)
    sleep(2)
    relay.action(1, Relay.State_Relay.OFF)

    relay.disconnect()
