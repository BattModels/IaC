# AllocatorTester.py
import time
from core.Allocator import Allocator
from core.Loader import load_iac_yaml
import threading
import os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "devices"))

# -------------------------------------------------------------------
# 1. Load IaC Resources
# -------------------------------------------------------------------
def load_resources():
    yaml_path = r"config/lab_config.yaml"  # update if needed
    print(f"Loading IaC YAML from: {yaml_path}")
    resources = load_iac_yaml(yaml_path)
    print(f"Loaded {len(resources)} resources.")
    return resources


# -------------------------------------------------------------------
# 2. Fake experiments to submit
# -------------------------------------------------------------------
def make_experiment(exp_id, group):
    return {
        "experiment_id": exp_id,
        "description": f"Fake experiment {exp_id}",
        "require_group": group
    }


# -------------------------------------------------------------------
# 3. Tester function
# -------------------------------------------------------------------
def test_allocator():
    resources = load_resources()
    print(resources)

    # Create allocator using IaC tree
    allocator = Allocator(resources)

    # Start background allocator threads
    allocator.start()

    # Create several experiments
    expA = make_experiment("EXP_A", "control_module")
    expB = make_experiment("EXP_B", "control_module")
    expC = make_experiment("EXP_C", "control_module")

    # Submit experiments in FIFO order
    print("\n=== SUBMITTING EXPERIMENTS ===")
    allocator.submit_experiment(expA)
    time.sleep(0.2)
    allocator.submit_experiment(expB)
    time.sleep(0.2)
    allocator.submit_experiment(expC)

    # Allow time for processing
    print("\n=== WAITING FOR ALLOCATOR ===")
    time.sleep(8)

    print("\n=== DONE ===")
    allocator.stop()


# -------------------------------------------------------------------
# Run tester
# -------------------------------------------------------------------
if __name__ == "__main__":
    test_allocator()

