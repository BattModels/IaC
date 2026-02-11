import json
from .TaskNode import TaskNode

def compile_experiment(json_path, resources):
    """
    Dynamic experiment compiler:
        - No hard-coding of equipment or actions
        - JSON-driven construction of TaskNode DAG
        - Uses actual resources loaded by IaC loader
    """

    spec = json.load(open(json_path))

    # ---- STEP 1: map logical resource names → actual resource objects ----
    logical_to_obj = {}
    print(resources)
    for resource_name in spec["resources"]:
        if resource_name not in resources:
            raise KeyError(
                f"Resource '{resource_name}' listed in experiment JSON but "
                f"not found in IaC resources."
            )
        logical_to_obj[resource_name] = resources[resource_name]
    print('Objects are:')
    print(logical_to_obj)
    # ---- STEP 2: create all TaskNode objects (without dependencies) ----
    nodes = {}
    for task in spec["tasks"]:
        print(task)
        task_id = task["task_id"]
        resource_obj = logical_to_obj[task["resource"]]

        node = TaskNode(
            task_id=task_id,
            resource=resource_obj,
            action=task["action"],
            args=task.get("args", []),
            kwargs=task.get("kwargs", {})
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
