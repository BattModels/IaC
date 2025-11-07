from datetime import datetime
from enum import Enum, auto
from abc import ABC, abstractmethod

class Status(Enum):
    AVAILABLE = auto()
    IN_USE = auto()
    ERROR = auto()

class Resource:
    def __init__(self, name=None, id=None, status=Status.AVAILABLE, parent=None, **attributes):
        self.name = name
        self.id = id
        self.status = status  # Use Status Enum
        self.parent = parent
        self.attributes = attributes
        self.children = []
        self.last_updated = datetime.now()

    def update_status(self, new_status: Status):
        """Update the status of the resource and refresh the last_updated timestamp."""
        if not isinstance(new_status, Status):
            raise ValueError("Status must be of type Status Enum")
        self.status = new_status
        self.last_updated = datetime.now()

    def add_child(self, child):
        self.children.append(child)
        child.parent = self

    def to_dict(self):
        """Convert recursively to dict"""
        data = {
            "name": self.name,
            "id": self.id,
            "status": self.status.name,  # store as string for serialization
            "last_updated": self.last_updated.strftime("%Y-%m-%d %H:%M:%S")
        }
        if self.attributes:
            data.update(self.attributes)
        if self.children:
            data["children"] = [c.to_dict() for c in self.children]
        return data
    
     # ---------- Abstract Methods ----------
    def connect(self):
        """Establish connection to the instrument and set status."""
        raise NotImplementedError("This method must be implemented by subclasses.")

    def disconnect(self):
        """Safely disconnect instrument and update status."""
        raise NotImplementedError("This method must be implemented by subclasses.")

    def action(self, *args, **kwargs):
        """Perform instrument-specific action (e.g., measurement)."""
        raise NotImplementedError("This method must be implemented by subclasses.")


    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name}, status={self.status.name}>"