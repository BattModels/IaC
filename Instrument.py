from abc import ABC, abstractmethod
from enum import Enum, auto
from pathlib import Path
import logging
try:
    from Resource import Resource, Status
except Exception as e:
    from .Resource import Resource, Status


# ----------------------------
# Connection Type Enum
# ----------------------------
class ConnectionType(Enum):
    SERIAL = auto()
    HID = auto()

# ----------------------------
# Base Instrument Class
# ----------------------------
class Instrument(Resource, ABC):
    """
    Abstract base class for lab instruments.
    Tracks status and handles logging.
    Supports serial and HID connection types.
    """

    def __init__(self, name: str, connection_type: ConnectionType, identifier, status, **attributes):
        super().__init__(name=name, status=status, **attributes)

        self.connection_type = connection_type

        # Set identifier and connection string based on type
        if self.connection_type == ConnectionType.SERIAL:
            if not isinstance(identifier, int):
                raise ValueError("For serial connection, identifier must be an integer.")
            self.identifier = identifier
            self.comm_port = f"COM{self.identifier}"
        elif self.connection_type == ConnectionType.HID:
            if not isinstance(identifier, (bytes, bytearray)):
                raise ValueError("For HID connection, identifier must be bytes.")
            self.identifier = identifier
            self.comm_port = identifier  # For HID, comm_port is the full device string
        else:
            raise ValueError(f"Unsupported connection type: {connection_type}")

        # Logging setup
        self.log_dir = Path("logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file_name = self.log_dir / f"{self.name}.log"
        self.logger = self._configure_logger()
        self.log(f"Initialized instrument {self.name} [{self.connection_type.name}] on {self.comm_port}")

    # ---------- Abstract Methods ----------
    @abstractmethod
    def connect(self):
        """Establish connection to the instrument and set status."""
        ...

    @abstractmethod
    def disconnect(self):
        """Safely disconnect instrument and update status."""
        ...

    @abstractmethod
    def action(self, *args, **kwargs):
        """Perform instrument-specific action (e.g., measurement)."""
        ...

    # ---------- Logging ----------
    def _configure_logger(self):
        logger = logging.getLogger(self.name)
        logger.setLevel(logging.INFO)
        if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
            handler = logging.FileHandler(self.log_file_name, mode='a')
            formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger

    def change_log_file(self, new_filename: str):
        new_path = Path(new_filename)
        new_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing file handlers
        for handler in self.logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                handler.close()
                self.logger.removeHandler(handler)

        # Add new handler
        new_handler = logging.FileHandler(new_path, mode='a')
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        new_handler.setFormatter(formatter)
        self.logger.addHandler(new_handler)

        self.log_file_name = new_path
        self.log(f"Switched log file to {new_path}")

    def get_status(self):
        """
        Return a dictionary representation of the instrument status.
        Subclasses can extend this to add additional fields (e.g., channel states).
        """
        return {}

    def log(self, message: str, level=logging.INFO):
        self.logger.log(level, message)