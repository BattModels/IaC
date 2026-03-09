from .MixingSolver import pulp_solve_sorted
import os
from datetime import datetime
import json
class NumberGenerator:
    def __init__(self, start: int = 0):
        self._start = start
        self._current = start

    def next(self) -> int:
        """Return current value and advance the counter."""
        value = self._current
        self._current += 1
        return value

    def current(self) -> int:
        """Return the current value without advancing."""
        return self._current

    def reset(self, start: int = None) -> None:
        """
        Reset the counter.
        If start is provided, reset to that value.
        Otherwise reset to the original starting value.
        """
        if start is not None:
            self._start = start
            self._current = start
        else:
            self._current = self._start

generator = NumberGenerator()
PRIME_VOLUME = 1.15
BALANCE_VOLUME = 0.5
BALANCE_TUBE_VOLUME = 0.7
BACK_FACTOR = 1.3
POTENTIOSTAT_VOLUME = 0.75
def nodes_to_id(nodes):
    result = []
    for current in nodes:
        result.append(current["task_id"])
    return result

def generate_node_graph(compositionID, module_name='clio_1', density=True, conductivity=True):
    resources = ["pump_1", "pump_2", "valve", "relay_1", "relay_2"]
    composition_list = pulp_solve_sorted(compositionID, df=None, prime=0.8, total_volume=0.5*(density + conductivity), tolerance=10E-6)
    nodes = []
    nodes.append({"task_id": generator.next(), "resource": module_name, "action": "create", "args": [], "kwargs": {}, "depends_on": []})
    current_dependents = nodes_to_id(nodes)
    current_stage = []
    current_stage.append({"task_id": generator.next(), "resource": "pump_1", "action": "create", "args": [], "kwargs": {}, "depends_on": current_dependents})
    current_stage.append({"task_id": generator.next(), "resource": "pump_2", "action": "create", "args": [], "kwargs": {}, "depends_on": current_dependents})
    current_stage.append({"task_id": generator.next(), "resource": "relay_1", "action": "create", "args": [], "kwargs": {}, "depends_on": current_dependents})
    current_stage.append({"task_id": generator.next(), "resource": "relay_2", "action": "create", "args": [], "kwargs": {}, "depends_on": current_dependents})
    current_stage.append({"task_id": generator.next(), "resource": "valve", "action": "create", "args": [], "kwargs": {}, "depends_on": current_dependents})
    if density:
        current_stage.append({"task_id": generator.next(), "resource": "balance", "action": "create", "args": [], "kwargs": {}, "depends_on": current_dependents})
        resources.append("balance")
    if conductivity:
        current_stage.append({"task_id": generator.next(), "resource": "palmsens4", "action": "create", "args": [], "kwargs": {}, "depends_on": current_dependents})
        resources.append("palmsens4")
    current_dependents = nodes_to_id(current_stage)
    nodes += current_stage
    for current in composition_list:
        if current[2] > 0:
            current_stage = []
            current_stage.append({"task_id": generator.next(), "resource": "valve", "action": "update", "args": [], "kwargs": {"dest":current[1] + 1}, "depends_on": current_dependents})
            current_stage.append({"task_id": generator.next(), "resource": "relay_1", "action": "update", "args": [], "kwargs": {"relay_num": 7, "state": 1}, "depends_on": current_dependents})
            current_stage.append({"task_id": generator.next(), "resource": "relay_1", "action": "update", "args": [], "kwargs": {"relay_num": 8, "state": 1}, "depends_on": current_dependents})
            current_dependents = nodes_to_id(current_stage)
            nodes += current_stage

            current_stage = [{"task_id": generator.next(), "resource": "pump_1", "action": "update", "args": [], "kwargs": {"flow_rate":5, "volume":PRIME_VOLUME, "direction":1}, "depends_on": current_dependents}]
            current_dependents = nodes_to_id(current_stage)
            nodes += current_stage

            current_stage = []
            current_stage.append({"task_id": generator.next(), "resource": "relay_1", "action": "update", "args": [], "kwargs": {"relay_num": 7, "state": 0}, "depends_on": current_dependents})
            current_stage.append({"task_id": generator.next(), "resource": "relay_1", "action": "update", "args": [], "kwargs": {"relay_num": 8, "state": 0}, "depends_on": current_dependents})
            current_dependents = nodes_to_id(current_stage)
            nodes += current_stage

            current_stage = [{"task_id": generator.next(), "resource": "pump_1", "action": "update", "args": [], "kwargs": {"flow_rate":5, "volume":current[2], "direction":1}, "depends_on": current_dependents}]
            current_dependents = nodes_to_id(current_stage)
            nodes += current_stage

    current_stage = [{"task_id": generator.next(), "resource": "valve", "action": "update", "args": [], "kwargs": {"dest":10}, "depends_on": current_dependents}]
    current_dependents = nodes_to_id(current_stage)
    nodes += current_stage
    current_stage = [{"task_id": generator.next(), "resource": "pump_1", "action": "update", "args": [], "kwargs": {"flow_rate":5, "volume":PRIME_VOLUME, "direction":0}, "depends_on": current_dependents}]
    current_dependents = nodes_to_id(current_stage)
    nodes += current_stage
    current_stage = [{"task_id": generator.next(), "resource": "relay_2", "action": "update", "args": [], "kwargs": {"relay_num":3, "state": 1}, "depends_on": current_dependents}]
    current_stage += [{"task_id": generator.next(), "resource": "relay_2", "action": "update", "args": [], "kwargs": {"relay_num":4, "state": 1}, "depends_on": current_dependents}]
    current_dependents = nodes_to_id(current_stage)
    nodes += current_stage
    current_stage = [{"task_id": generator.next(), "wait": 10, "depends_on": current_dependents}]
    current_dependents = nodes_to_id(current_stage)
    nodes += current_stage
    current_stage = [{"task_id": generator.next(), "resource": "relay_2", "action": "update", "args": [], "kwargs": {"relay_num":3, "state": 0}, "depends_on": current_dependents}]
    current_stage += [{"task_id": generator.next(), "resource": "relay_2", "action": "update", "args": [], "kwargs": {"relay_num":4, "state": 0}, "depends_on": current_dependents}]
    current_dependents = nodes_to_id(current_stage)
    nodes += current_stage
    current_stage = [{"task_id": generator.next(), "wait": 30, "depends_on": current_dependents}]
    current_dependents = nodes_to_id(current_stage)
    nodes += current_stage



    if density:
        current_stage = [{"task_id": generator.next(), "resource": "relay_1", "action": "update", "args": [], "kwargs": {"relay_num":1, "state": 1}, "depends_on": current_dependents}]
        current_stage += [{"task_id": generator.next(), "resource": "relay_1", "action": "update", "args": [], "kwargs": {"relay_num":2, "state": 1}, "depends_on": current_dependents}]
        current_dependents = nodes_to_id(current_stage)
        nodes += current_stage
        current_stage = [{"task_id": generator.next(), "resource": "pump_2", "action": "update", "args": [], "kwargs": {"flow_rate":4, "volume":BALANCE_TUBE_VOLUME, "direction":1}, "depends_on": current_dependents}]
        current_dependents = nodes_to_id(current_stage)
        nodes += current_stage
        current_stage = [{"task_id": generator.next(), "resource": "balance", "action": "read", "args": [], "kwargs": {}, "depends_on": current_dependents}]
        current_dependents = nodes_to_id(current_stage)
        nodes += current_stage
        current_stage = [{"task_id": generator.next(), "resource": "pump_2", "action": "update", "args": [], "kwargs": {"flow_rate":4, "volume":BALANCE_VOLUME, "direction":1}, "depends_on": current_dependents}]
        current_dependents = nodes_to_id(current_stage)
        nodes += current_stage
        current_stage = [{"task_id": generator.next(), "resource": "balance", "action": "read", "args": [], "kwargs": {}, "depends_on": current_dependents}]
        current_dependents = nodes_to_id(current_stage)
        nodes += current_stage
        nodes += [{"task_id": generator.next(), "resource": "balance", "action": "delete", "args": [], "kwargs": {}, "depends_on": current_dependents}]
        current_stage = [{"task_id": generator.next(), "resource": "pump_2", "action": "update", "args": [], "kwargs": {"flow_rate":4, "volume":BALANCE_TUBE_VOLUME * BACK_FACTOR, "direction":0}, "depends_on": current_dependents}]
        current_dependents = nodes_to_id(current_stage)
        nodes += current_stage
        current_stage = [{"task_id": generator.next(), "resource": "relay_1", "action": "update", "args": [], "kwargs": {"relay_num":1, "state": 0}, "depends_on": current_dependents}]
        current_stage += [{"task_id": generator.next(), "resource": "relay_1", "action": "update", "args": [], "kwargs": {"relay_num":2, "state": 0}, "depends_on": current_dependents}]
        current_dependents = nodes_to_id(current_stage)
        nodes += current_stage

    if conductivity:
        current_stage = [{"task_id": generator.next(), "resource": "relay_1", "action": "update", "args": [], "kwargs": {"relay_num":3, "state": 1}, "depends_on": current_dependents}]
        current_stage += [{"task_id": generator.next(), "resource": "relay_1", "action": "update", "args": [], "kwargs": {"relay_num":4, "state": 1}, "depends_on": current_dependents}]
        current_dependents = nodes_to_id(current_stage)
        nodes += current_stage
        current_stage = [{"task_id": generator.next(), "resource": "pump_2", "action": "update", "args": [], "kwargs": {"flow_rate":5, "volume":POTENTIOSTAT_VOLUME, "direction":1}, "depends_on": current_dependents}]
        current_dependents = nodes_to_id(current_stage)
        nodes += current_stage
        current_stage = [{"task_id": generator.next(), "resource": "palmsens4", "action": "update", "args": [], "kwargs": {"eac":0.25, "freq_min": 2.0e4, "freq_max": 5.92e5, "n_freq": 10}, "depends_on": current_dependents}]
        current_dependents = nodes_to_id(current_stage)
        nodes += current_stage
        current_stage = [{"task_id": generator.next(), "resource": "palmsens4", "action": "read", "args": [], "kwargs": {}, "depends_on": current_dependents}]
        current_dependents = nodes_to_id(current_stage)
        nodes += current_stage
        nodes += [{"task_id": generator.next(), "resource": "palmsens4", "action": "delete", "args": [], "kwargs": {}, "depends_on": current_dependents}]
        current_stage = [{"task_id": generator.next(), "resource": "pump_2", "action": "update", "args": [], "kwargs": {"flow_rate":4, "volume":POTENTIOSTAT_VOLUME * BACK_FACTOR, "direction":0}, "depends_on": current_dependents}]
        current_dependents = nodes_to_id(current_stage)
        nodes += current_stage
        current_stage = [{"task_id": generator.next(), "resource": "relay_1", "action": "update", "args": [], "kwargs": {"relay_num":3, "state": 0}, "depends_on": current_dependents}]
        current_stage += [{"task_id": generator.next(), "resource": "relay_1", "action": "update", "args": [], "kwargs": {"relay_num":4, "state": 0}, "depends_on": current_dependents}]
        current_dependents = nodes_to_id(current_stage)
        nodes += current_stage

    current_stage = [{"task_id": generator.next(), "resource": "pump_2", "action": "update", "args": [], "kwargs": {"flow_rate":5, "volume":1.5, "direction":0}, "depends_on": current_dependents}]
    current_dependents = nodes_to_id(current_stage)
    nodes += current_stage

    current_stage = []
    current_stage.append({"task_id": generator.next(), "resource": "pump_1", "action": "delete", "args": [], "kwargs": {}, "depends_on": current_dependents})
    current_stage.append({"task_id": generator.next(), "resource": "pump_2", "action": "delete", "args": [], "kwargs": {}, "depends_on": current_dependents})
    current_stage.append({"task_id": generator.next(), "resource": "relay_1", "action": "delete", "args": [], "kwargs": {}, "depends_on": current_dependents})
    current_stage.append({"task_id": generator.next(), "resource": "relay_2", "action": "delete", "args": [], "kwargs": {}, "depends_on": current_dependents})
    current_stage.append({"task_id": generator.next(), "resource": "valve", "action": "delete", "args": [], "kwargs": {}, "depends_on": current_dependents})
    current_dependents = nodes_to_id(current_stage)
    nodes += current_stage

    nodes.append({"task_id": generator.next(), "resource": module_name, "action": "delete", "args": [], "kwargs": {}, "depends_on": current_dependents})

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment = {"experiment_id": timestamp,
    "resources": resources, "module": module_name, "tasks": nodes}

    current_dir = os.path.dirname(os.path.abspath(__file__))
    target_dir = os.path.join(current_dir, '..', 'Experiment_Sessions')
    
    filename = f"{timestamp}.json"
    filepath = os.path.join(target_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(experiment, f, indent=4)

    return filepath