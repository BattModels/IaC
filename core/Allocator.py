import threading
import time
from queue import Queue
from typing import Dict, Any, Optional
from core.Resource import Resource

class Allocator:
    """
    Thread-safe, FIFO-fair resource allocator.
    Two cooperating threads:
        1) intake_thread  → receives experiments and enqueues them
        2) dispatch_thread → always checks HEAD of the queue only
    """

    def __init__(self, resource_graph):
        self.resource_graph = resource_graph   # full IaC tree
        self.request_queue = Queue()           # FIFO experiment queue
        self.running = True                    # stop flag

        self.lock = threading.Lock()           # protects resource state
        self.active_experiments: Dict[str, Any] = {}  # exp_id → allocation info

        # Background threads
        self.intake_thread = threading.Thread(target=self._intake_loop, daemon=True)
        self.dispatch_thread = threading.Thread(target=self._dispatch_loop, daemon=True)

    # ----------------------------------------------------------------------
    # External API: submit new experiment
    # ----------------------------------------------------------------------
    def submit_experiment(self, exp_spec: Dict[str, Any]):
        """Called by user / agent to enqueue a new experiment."""
        print(f"[Allocator] Received experiment request: {exp_spec['experiment_id']}")
        self.request_queue.put(exp_spec)

    # ----------------------------------------------------------------------
    # Intake (simple loop to wait for new experiments)
    # ----------------------------------------------------------------------
    def _intake_loop(self):
        """This loop exists in case we want to add pre-processing later."""
        while self.running:
            time.sleep(0.2)

    # ----------------------------------------------------------------------
    # Main dispatch loop (head-of-line scheduling)
    # ----------------------------------------------------------------------
    def _dispatch_loop(self):
        """
        Conservative backfilling:
        - Always protect the HEAD job's required device type.
        - Backfill ONLY with jobs that do NOT need that device type.
        """

        while self.running:
            if self.request_queue.empty():
                time.sleep(0.1)
                continue

            # --------------------------
            # 1. HEAD OF LINE JOB
            # --------------------------
            queue_list = list(self.request_queue.queue)
            head_spec = queue_list[0]
            head_id = head_spec["experiment_id"]
            head_group = head_spec["require_group"]

            print(f"[Allocator] Checking HEAD job {head_id} (group={head_group})")

            # Try to allocate the head job
            head_alloc = self._attempt_allocation(head_spec)

            if head_alloc is not None:
                # Head job can run NOW → run it
                print(f"[Allocator] HEAD job {head_id} allocated (reserved resource is now free).")
                self._pop_and_run(head_spec, head_alloc)
                continue

            # If head cannot run, we RESERVE its device type
            print(f"[Allocator] HEAD job {head_id} cannot run. Reserving group '{head_group}'.")

            # --------------------------
            # 2. BACKFILL
            # Only backfill jobs that DO NOT require the reserved group.
            # --------------------------
            backfilled = False

            for spec in queue_list[1:]:
                exp_id = spec["experiment_id"]
                group = spec["require_group"]

                # Skip jobs that might delay the head job
                if group == head_group:
                    print(f"[Allocator] Skipping {exp_id}: conflicts with HEAD reservation.")
                    continue

                # Only try jobs that use DIFFERENT resources
                alloc = self._attempt_allocation(spec)

                if alloc is not None:
                    print(f"[Allocator] Backfilling safe job {exp_id} (no conflict with head).")
                    self._pop_and_run(spec, alloc)
                    backfilled = True
                    break

            if not backfilled:
                print("[Allocator] No safe jobs to run. Waiting...")
                time.sleep(0.5)

    # ----------------------------------------------------------------------
    # Resource allocation logic (chooses group)
    # ----------------------------------------------------------------------
    def _attempt_allocation(self, exp_spec):
        required_group = exp_spec["require_group"]

        with self.lock:
            available = []

            # Scan the resource graph for ControlModule, Pump groups, etc.
            for res_name, res_obj in self.resource_graph.items():

                # Only match resources of the correct type (group)
                if not hasattr(res_obj, "type_name"):
                    continue

                if res_obj.type_name != required_group:
                    continue

                # Check availability
                if getattr(res_obj, "status", None).name == "AVAILABLE":
                    available.append(res_obj)

            if not available:
                return None  # allocation impossible now

            chosen = available[0]  # FIFO, simplest selection
            chosen.status = Resource.Status.IN_USE
            return chosen

    # ----------------------------------------------------------------------
    # Run experiment after allocation
    # ----------------------------------------------------------------------
    def _run_experiment(self, exp_spec, allocated_resource):
        exp_id = exp_spec["experiment_id"]
        print(f"[Executor] Running {exp_id} on resource group {allocated_resource.name}")

        # TODO: call your TaskNode compiler + DAG runner here

        time.sleep(1)  # placeholder simulation

        # Mark resource free
        with self.lock:
            allocated_resource.status = Resource.Status.AVAILABLE

        print(f"[Executor] Experiment {exp_id} completed — resource released.")

    # ----------------------------------------------------------------------
    # Start allocator threads
    # ----------------------------------------------------------------------
    def start(self):
        print("[Allocator] Starting allocator threads...")
        self.intake_thread.start()
        self.dispatch_thread.start()

    # ----------------------------------------------------------------------
    # Stop allocator
    # ----------------------------------------------------------------------
    def stop(self):
        self.running = False
        print("[Allocator] Stopping...")

        # ----------------------------------------------------------------------
    # Utility: pop a specific experiment (not only head!)
    # ----------------------------------------------------------------------
    def _pop_and_run(self, exp_spec, allocated_resource):
        """Remove the given experiment from the queue and start execution."""

        # Build a new queue WITHOUT this exp_spec
        new_queue = Queue()
        for item in list(self.request_queue.queue):
            if item != exp_spec:
                new_queue.put(item)
        self.request_queue = new_queue

        # Launch experiment in a new thread
        t = threading.Thread(
            target=self._run_experiment,
            args=(exp_spec, allocated_resource),
            daemon=True
        )
        t.start()
