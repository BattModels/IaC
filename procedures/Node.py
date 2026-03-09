import time
from typing import Any, List, Optional, Set


class Node:
    """
    Generic DAG node.
    Handles dependency relationships and execution state.
    """

    def __init__(self, node_id: str, depends_on: Optional[List["Node"]] = None):
        self.id = node_id
        self.depends_on: Set["Node"] = set(depends_on or [])
        self.is_prerequisite_of: Set["Node"] = set()

        # register reverse edges
        for dep in self.depends_on:
            dep.is_prerequisite_of.add(self)

        # runtime fields
        self.completed = False
        self.result = None

    def is_ready(self) -> bool:
        """Node is ready if all dependencies are completed."""
        return all(node.completed for node in self.depends_on)
    
    def run(self):
        return 0


    def __repr__(self):
        return f"<Node id={self.id}, completed={self.completed}>"
    