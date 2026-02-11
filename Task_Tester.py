import os, sys
import json
from core.Loader import load_iac_yaml
from procedures.Compiler import compile_experiment      # your compiler
from procedures.TaskNode import TaskNode
from collections import deque
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "devices"))
from typing import List, Dict, Any

def run_experiment(tasks: List[TaskNode]) -> Dict[str, Any]:
    """
    Execute a list of TaskNodes as a DAG:
      - Only run tasks whose dependencies are completed (TaskNode.depends_on)
      - Respect resource availability (TaskNode.is_ready)
      - Resolve kwargs of the form {"input_from": "<task_id>"} using previous results
    Returns:
      dict mapping task_id -> result
    """
    remaining = set(tasks)
    available = deque()
    for current in tasks:
        if not current.depends_on:
            available.append(current)


    while available:

        node = available.popleft()



        print(f"[RUN] {node.task_id}: {node.resource.name}.{node.action}(*{node.args}, **{node.kwargs})")
        res = node.run()

        node.result = res
        remaining.remove(node)
        for current in node.is_prerequisite_of:
            current.depends_on.remove(node)
            if not current.depends_on:
                available.append(current)


    if remaining:
        # No progress in this iteration → dependency cycle or blocked resource
        stuck = ", ".join([task.name for task in remaining])
        raise RuntimeError(f"Deadlock: no runnable tasks. Remaining: {stuck}")

    return


def run_task_tester(resources):
    ROOT = os.path.dirname(os.path.abspath(__file__))

    # --------------------------
    # 1. Load IaC resources
    # --------------------------


    # --------------------------
    # 2. Load JSON experiment
    # --------------------------
    json_path = os.path.join(ROOT, "Experiment_Sessions", "TestExperiment.json")
    print(f"Loading experiment JSON from: {json_path}")

    task_nodes = compile_experiment(json_path, resources)

    # --------------------------
    # 3. Execute DAG
    # --------------------------
    run_experiment(task_nodes)

if __name__ == '__main__':
    resources = load_iac_yaml("config/temp.yaml")
    run_task_tester(resources)