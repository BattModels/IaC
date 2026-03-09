from typing import List, Optional, Any
import time
from .Node import Node
class WaitNode(Node):
    """
    A node in the experiment DAG.
    Each node corresponds to a single actionable step on a resource.
    """

    def __init__(
        self,
        task_id: str,
        wait,
        depends_on: Optional[List[Node]] = None
    ):
        super().__init__(node_id=task_id, depends_on=depends_on)
        self.wait = wait

    def run(self):
        """Execute the task on its resource."""
        time.sleep(self.wait)
        return 0

    def __repr__(self):
        return (
            f"<TaskNode id={self.id}, wait_time={self.wait}, "
            f"completed={self.completed}>"
        )