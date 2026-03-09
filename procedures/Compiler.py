import json
from typing import List, Dict, Any
from .TaskNode import TaskNode
from .WaitNode import WaitNode
from .Node import Node
from collections import deque
def compile_experiment(spec, resources):
    """
    Dynamic experiment compiler:
        - No hard-coding of equipment or actions
        - JSON-driven construction of TaskNode DAG
        - Uses actual resources loaded by IaC loader
    """

    # ---- STEP 1: map logical resource names → actual resource objects ----
    logical_to_obj = {}
    logical_to_obj[spec["module"]] = resources[spec["module"]]
    available_resources = {}
    for current in logical_to_obj[spec["module"]].equipment:
        available_resources[current.name] = current
    for current in logical_to_obj[spec["module"]].endpoints:
        available_resources[current.name] = current
    for resource_name in spec["resources"]:
        if resource_name not in available_resources:
            raise KeyError(
                f"Resource '{resource_name}' listed in experiment JSON but "
                f"not found in IaC resources."
            )
        logical_to_obj[resource_name] = available_resources[resource_name]
    print('Objects are:')
    # ---- STEP 2: create all TaskNode objects (without dependencies) ----
    nodes = {}
    for task in spec["tasks"]:
        print(task)
        task_id = task["task_id"]
        if "resource" in task:
            resource_obj = logical_to_obj[task["resource"]]

            node = TaskNode(
                task_id=task_id,
                resource=resource_obj,
                action=task["action"],
                args=task.get("args", []),
                kwargs=task.get("kwargs", {})
            )
        elif "wait" in task:
            node = WaitNode(
                task_id=task_id,
                wait = task["wait"]
            )
        nodes[task_id] = node

    # ---- STEP 3: connect dependencies dynamically ----
    for task in spec["tasks"]:
        task_id = task["task_id"]
        deps = task.get("depends_on", [])

        for dep_id in deps:
            if dep_id not in nodes:
                raise KeyError(f"Unknown dependency '{dep_id}' in task '{task_id}'")
            nodes[task_id].depends_on.add(nodes[dep_id])
            nodes[dep_id].is_prerequisite_of.add(nodes[task_id])

    # ---- STEP 4: return the DAG (root tasks are those with no dependencies) ----
    return list(nodes.values())

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