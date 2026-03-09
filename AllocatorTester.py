# AllocatorTester.py
import time
from core.Allocator import Allocator
from core.Loader import load_iac_yaml
import threading
import os, sys
import json
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "devices"))


# -------------------------------------------------------------------
# Run tester
# -------------------------------------------------------------------
def tester(allocator):
    with open("Experiment_Sessions/20260308_193455.json", "r") as f:
        spec = json.load(f)
    allocator.submit_experiment(spec)
    with open("Experiment_Sessions/20260308_193456.json", "r") as f:
        spec = json.load(f)
    allocator.submit_experiment(spec)
    with open("Experiment_Sessions/20260308_193915.json", "r") as f:
        spec = json.load(f)
    allocator.submit_experiment(spec)
    time.sleep(750)

if __name__ == '__main__':
    resources = load_iac_yaml("config/temp.yaml")
    allocator = Allocator(resources)
    tester(allocator)