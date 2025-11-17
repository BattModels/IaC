from datetime import datetime
from enum import Enum, auto
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional





class Resource(ABC):
    """
    Terraform-friendly base resource model.

    Terraform (or any IaC layer) is expected to:
      - pass a *desired_state* dict into `create` or `update`
      - call `read` to obtain *actual_state* for reconciliation.

    Both desired_state and actual_state are plain dicts so that they can be
    serialized into Terraform state files or sent over RPC.
    """
    class Status(Enum):
        AVAILABLE = auto()
        IN_USE = auto()
        ERROR = auto()

    def __init__(self, name: str, id, desired_state: Optional[Dict[str, Any]] = None) -> None:
        self.name = name
        self.id = id
        self.status: Resource.Status = Resource.Status.AVAILABLE
        self.desired_state: Dict[str, Any] = desired_state or {}
        self.actual_state: Dict[str, Any] = {}
        self.last_updated: datetime = datetime.utcnow()

    # ---------- State helpers ----------

    def set_desired_state(self, state: Dict[str, Any]) -> None:
        """Replace desired_state with a new config."""
        self.desired_state = dict(state)
        self.touch()

    def merge_desired_state(self, state: Dict[str, Any]) -> None:
        """Shallow-merge new keys into desired_state."""
        self.desired_state.update(state)
        self.touch()

    def update_actual_state(self, state: Dict[str, Any]) -> None:
        """Replace actual_state after a device poll."""
        self.actual_state = dict(state)
        self.touch()

    def update_status(self, new_status: Status) -> None:
        if not isinstance(new_status, Resource.Status):
            raise ValueError("Status must be a Status enum value.")
        self.status = new_status
        self.touch()

    def touch(self) -> None:
        self.last_updated = datetime.utcnow()

    # ---------- Terraform-style lifecycle ----------

    @abstractmethod
    def create(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Provision / connect the resource and bring it to the desired state.

        `config` is merged into desired_state; the resulting actual_state
        *must* be returned as a plain dict.
        """
        raise NotImplementedError

    @abstractmethod
    def read(self) -> Dict[str, Any]:
        """Return the current actual_state as a plain dict."""
        raise NotImplementedError

    @abstractmethod
    def update(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reconcile the resource to match the new desired config.
        Returns updated actual_state.
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self) -> None:
        """Tear down / disconnect the resource."""
        raise NotImplementedError

    # ---------- Diff & serialization ----------

    def diff(self) -> Dict[str, Dict[str, Any]]:
        """
        Compare desired_state vs actual_state.

        This is exactly the kind of structure a Terraform provider can surface
        for debugging drift.
        """
        return {
            key: {"current": self.actual_state.get(key), "desired": desired}
            for key, desired in self.desired_state.items()
            if self.actual_state.get(key) != desired
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize minimal resource info to a Terraform/state-friendly dict."""
        return {
            "name": self.name,
            "status": self.status.name,
            "desired_state": self.desired_state,
            "actual_state": self.actual_state,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Resource":
        """
        Helper mainly for tests or higher-level orchestration; concrete subclasses
        may override this if they need extra fields.
        """
        obj = cls(name=data["name"], desired_state=data.get("desired_state") or {})
        obj.status = Resource.Status[data.get("status", "AVAILABLE")]
        obj.actual_state = data.get("actual_state") or {}
        if "last_updated" in data:
            try:
                obj.last_updated = datetime.fromisoformat(data["last_updated"])
            except Exception:
                obj.last_updated = datetime.utcnow()
        return obj

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name}, status={self.status}>"
