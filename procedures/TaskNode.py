from typing import List, Optional, Any
import time
from .Node import Node
class TaskNode(Node):
    """
    A node in the experiment DAG.
    Each node corresponds to a single actionable step on a resource.
    """

    def __init__(
        self,
        task_id: str,
        resource: Any,          # Instrument instance
        action: str,            # method name of the instrument ("update", "create", etc.)
        args: Optional[List] = None,
        kwargs: Optional[dict] = None,
        depends_on: Optional[List[Node]] = None
    ):
        super().__init__(node_id=task_id, depends_on=depends_on)

        self.resource = resource
        self.action = action
        self.args = args or []
        self.kwargs = kwargs or {}

    def run(self):
        """Execute the task on its resource."""
        if not self.is_ready():
            raise RuntimeError(f"Task {self.id} is not ready to run.")

        method = getattr(self.resource, self.action)
        self.result = method(*self.args, **self.kwargs)
        self.completed = True

        time.sleep(1)
        return 0

    def __repr__(self):
        return (
            f"<TaskNode id={self.id}, action={self.action}, "
            f"completed={self.completed}>"
        )
    