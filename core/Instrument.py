from abc import ABC, abstractmethod
from enum import Enum, auto
from pathlib import Path
import logging
from typing import Any
import base64
from core.Resource import Resource
from typing import Any, Dict, Optional

class ConnectionType(Enum):
    SERIAL = auto()
    HID = auto()


class Instrument(Resource, ABC):
    """
    Base class for all lab instruments.
    Defines the Terraform-like lifecycle API:
        - create()
        - read()
        - update(...)
        - delete()

    Subclasses MUST implement all 4 methods.
    """

    def __init__(self, name: str, id, type_name, connection_type: ConnectionType,
                 identifier: Any, desired_state: Optional[Dict[str, Any]] = None, log_dir="logs"):
        super().__init__(name=name, type_name=type_name, id=id)
        
        self.connection_type = connection_type
        self.identifier = identifier
        self.comm_port = None
        if isinstance(self.identifier, str):
            # YAML gives base64-encoded bytes → decode it
            
            try:
                decoded = base64.b64decode(self.identifier)
            except Exception:
                raise ValueError(f"Invalid HID address (not base64): {self.identifier}")

            self.identifier = decoded

        # Connection port resolution
        if connection_type == ConnectionType.SERIAL:
            self.comm_port = f"COM{int(identifier)}"
        elif connection_type == ConnectionType.HID:
            self.comm_port = identifier
        else:
            raise ValueError(f"Unsupported connection type: {connection_type}")

        # Logging
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.log_file_path = self.log_dir / f"{self.name}.log"
        self.logger = self._configure_logger()
        self.log(f"[INIT] {self.name} / {connection_type.name} @ {self.comm_port}")

    # ==========================================================
    # Abstract lifecycle methods — subclasses MUST override
    # ==========================================================
    @abstractmethod
    def create(self):
        """Connect device, allocate resource, hardware initialization."""
        ...

    def read(self):
        """Return device status, including hardware polling if needed."""
        self.actual_state['status'] = self.status
        return {'diff': self.diff(), 'state':self.actual_state}
    
    def update(self, *args, **kwargs):
        """Perform device operation (move valve, set flow rate, etc)."""
        return

    @abstractmethod
    def delete(self):
        """Disconnect safely and release the device."""
        ...

    # ==========================================================
    # Logging utilities
    # ==========================================================
    def _configure_logger(self):
        logger = logging.getLogger(self.name)
        logger.setLevel(logging.INFO)

        handler = logging.FileHandler(self.log_file_path, mode='a')
        handler.setFormatter(
            logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        )
        logger.addHandler(handler)

        return logger

    def log(self, msg, level=logging.INFO):
        self.logger.log(level, msg)
