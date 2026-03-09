import os, sys
import json
from core.Loader import load_iac_yaml
from procedures.Compiler import compile_experiment      # your compiler
from procedures.Node import Node
from collections import deque
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "devices"))
from typing import List, Dict, Any

def run_experiment(tasks: List[Node]) -> Dict[str, Any]:
    """
    Execute tasks as a DAG with failure cleanup.
    If any task fails:
        - Stop execution
        - Delete all created resources
    """

    remaining = set(tasks)
    available = deque()
    completed = []
    created_resources = set()
    results = {}

    # Initialize queue
    for node in tasks:
        if not node.depends_on:
            available.append(node)

    try:
        while available:

            node = available.popleft()
            print(f"Running: {node.id}")

            # Run task
            res = node.run()

            node.result = res
            results[node.id] = res
            completed.append(node)
            remaining.remove(node)

            # Track created resources
            try:
                if node.resource.is_error():
                    raise BufferError(f"Resource {node.resource.name} has an error.")
                if node.action == "create":
                    created_resources.add(node.resource)
            except AttributeError as e:
                pass

            # Schedule next tasks
            for nxt in node.is_prerequisite_of:
                nxt.depends_on.remove(node)
                if not nxt.depends_on:
                    available.append(nxt)

        if remaining:
            stuck = ", ".join([task.id for task in remaining])
            raise RuntimeError(f"Deadlock detected. Remaining: {stuck}")

    except Exception as e:
        print(f"\nExperiment failed: {e}")
        print("Starting cleanup...")

        # Cleanup created resources
        for resource in created_resources:
            try:
                print(f"Deleting resource: {resource}")
                resource.delete()
            except Exception as cleanup_error:
                print(f"Cleanup failed for {resource}: {cleanup_error}")

        raise  # re-raise original exception

    return results


def run_task_tester(resources):
    ROOT = os.path.dirname(os.path.abspath(__file__))

    # --------------------------
    # 1. Load IaC resources
    # --------------------------


    # --------------------------
    # 2. Load JSON experiment
    # --------------------------
    json_path = os.path.join(ROOT, "Experiment_Sessions", "20260302_170002.json")
    print(f"Loading experiment JSON from: {json_path}")

    task_nodes = compile_experiment(json_path, resources)

    # --------------------------
    # 3. Execute DAG
    # --------------------------
    run_experiment(task_nodes)

if __name__ == '__main__':
    resources = load_iac_yaml("config/temp.yaml")
    run_task_tester(resources)