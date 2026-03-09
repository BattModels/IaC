import threading
import time
from queue import Queue
from collections import defaultdict
from typing import Dict, Any, Optional, List, Tuple

from core.Resource import Resource
try:
    from ..procedures.Compiler import compile_experiment, run_experiment
except Exception as e:
    from procedures.Compiler import compile_experiment, run_experiment

class Allocator:
    """
    Allocator that schedules experiments by *control module type*.

    - One FIFO queue per module type (e.g., "clio", "other_module_type")
    - Each module type has a dedicated dispatch loop thread
    - Dispatch loop:
        - Takes HEAD experiment of that type
        - Allocates one AVAILABLE module instance of that type
        - Runs the experiment DAG bound to that module instance
        - Releases the module instance when done

    Requirements on your resource graph:
    - `resources` is a dict: module_instance_name -> module_obj
    - module_obj has:
        - .type_name (e.g., "clio")
        - .status (Resource.Status.*)
        - .equipment (iterable of device resources, each with .name)
        - .endpoints (iterable of endpoint resources, each with .name)
    """

    def __init__(
        self,
        resources: Dict[str, Any],
        poll_interval_s: float = 0.05,
    ):
        self.resources = resources
        self.poll_interval_s = poll_interval_s

        # module_type -> FIFO queue of experiment specs
        self.queues: Dict[str, Queue] = defaultdict(Queue)

        # module_type -> dispatch thread
        self.dispatch_threads: Dict[str, threading.Thread] = {}

        # Protects:
        # - module instance status transitions
        # - dispatch thread creation
        self.lock = threading.Lock()

        self.running = True

    # ------------------------------------------------------------------
    # External API
    # ------------------------------------------------------------------
    def submit_experiment(self, exp_spec: Dict[str, Any]) -> None:
        """
        exp_spec must include:
          - "experiment_id"
          - "module" : module TYPE (recommended) OR module instance name (supported)
        If exp_spec["module"] equals a module instance name in resources, we treat it
        as an instance; otherwise treat it as a type.
        """
        if "experiment_id" not in exp_spec:
            raise KeyError("exp_spec missing required field: 'experiment_id'")
        if "module" not in exp_spec:
            raise KeyError("exp_spec missing required field: 'module'")

        module_key = exp_spec["module"]

        # Decide if exp_spec["module"] is an instance name or a type name
        if module_key in self.resources:
            # module_key is an instance name like "clio_1"
            module_type = getattr(self.resources[module_key], "module_type", None)
            if module_type is None:
                raise AttributeError(f"Module instance '{module_key}' missing .module_type")
        else:
            # module_key is a module type like "clio"
            module_type = module_key

        self.queues[module_type].put(exp_spec)

        # Ensure a dispatch thread exists for this module type
        with self.lock:
            if module_type not in self.dispatch_threads:
                t = threading.Thread(
                    target=self._dispatch_loop,
                    args=(module_type,),
                    daemon=True,
                )
                self.dispatch_threads[module_type] = t
                t.start()

    def stop(self) -> None:
        self.running = False

    # ------------------------------------------------------------------
    # Dispatch logic
    # ------------------------------------------------------------------
    def _dispatch_loop(self, module_type: str) -> None:
        """
        Head-of-line, per-type FIFO:
          - Only consider the HEAD experiment in this type queue.
          - Run it as soon as a module instance of this type becomes available.
        """
        print('here')
        q = self.queues[module_type]
        while self.running:
            if q.empty():
                time.sleep(self.poll_interval_s)
                continue

            exp_spec = q.queue[0]  # peek head
            pick = self._try_allocate_module(module_type)
            if pick is None:
                time.sleep(self.poll_interval_s)
                continue
            instance_name, instance_obj = pick
            print(f"Picked: {instance_obj.status}")
            instance_obj.create()
            # Pop now that we have reserved a module instance
            q.get()
            # Run experiment in background
            threading.Thread(
                target=self._run_on_instance,
                args=(exp_spec, instance_name, instance_obj),
                daemon=True,
            ).start()

            time.sleep(1)

    def _try_allocate_module(self, module_type: str) -> Optional[Tuple[str, Any]]:
        """
        Find an AVAILABLE module instance matching module_type and reserve it (IN_USE).
        """
        with self.lock:
            for instance_name, module_obj in self.resources.items():
                if getattr(module_obj, "module_type", None) != module_type:
                    continue
                if getattr(module_obj, "status", None) == Resource.Status.AVAILABLE:
                    thread_id = threading.get_ident()
                    print(f"Running in thread ID: {thread_id}")
                    module_obj.status = Resource.Status.IN_USE
                    return instance_name, module_obj
        return None

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def _run_on_instance(self, exp_spec: Dict[str, Any], instance_name: str, instance_obj: Any) -> None:
        exp_id = exp_spec.get("experiment_id", "<unknown>")
        try:
            # Bind experiment to the chosen instance.
            # Your compiler currently does: resources[spec["module"]] to find the module object.
            # So we create a shallow copy of resources and map the instance name to the instance_obj.
            # Then we rewrite exp_spec["module"] to be the instance_name.
            bound_spec = dict(exp_spec)
            for current in bound_spec['tasks']:
                try:
                    if current['resource'] == bound_spec["module"]:
                        current['resource'] = instance_name
                except Exception as e:
                    pass
            bound_spec["module"] = instance_name
            # Compile & run
            task_nodes = self.compile_experiment_from_spec(bound_spec)
            run_experiment(task_nodes)

        except Exception as e:
            # IMPORTANT: you may want to trigger a cleanup DAG here
            # (e.g., stop pumps, set relays OFF, delete created resources)
            print(f"[Allocator] Experiment {exp_id} failed on {instance_name}: {e}")
            raise e

    def compile_experiment_from_spec(self, bound_spec: Dict[str, Any]):
        """
        Your existing compiler signature is:
          compile_experiment(json_path, resources)

        But now we often have a dict spec in memory.
        This helper supports either:
          - bound_spec has "json_path" -> call compiler(json_path, resources)
          - otherwise compile from dict by writing temp file (simple & robust),
            OR you can modify your compiler to accept a dict directly.

        For minimal changes, we support both.
        """

        return compile_experiment(bound_spec, self.resources)

    def snapshot_queues(self) -> Dict[str, Any]:
        """
        Return a GUI-safe snapshot of all queues + which module instances are busy.
        No mutation; shallow copies only.
        """
        with self.lock:
            queues = {}
            for module_type, q in self.queues.items():
                # Copy the underlying deque safely enough for GUI polling.
                items = list(q.queue)
                queues[module_type] = [
                    {
                        "experiment_id": spec.get("experiment_id"),
                        "module_request": spec.get("module"),
                        "n_tasks": len(spec.get("tasks", [])),
                    }
                    for spec in items
                ]


        return {"queues": queues}