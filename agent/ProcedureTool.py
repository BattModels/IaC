from collections import deque
from langchain_core.tools import tool
import os, json
try:
    # Try relative imports first (for modular usage)
    from Loader import load_lab_config, resource_map
    from Pump import *
    from Viscometer import *
    from Relay import *
    from Procedure import Procedure, ResourceProcedure, WaitProcedure, GenerateProcedure
    from Inventory_Manager import InventoryMode
    from Utils import *
except Exception as e:
    # Fallback to package-style imports (when running as part of a module)
    from .Loader import load_lab_config, resource_map
    from .Pump import *
    from .Viscometer import *
    from .Relay import *
    from .Procedure import Procedure, ResourceProcedure, WaitProcedure, GenerateProcedure
    from Inventory_Manager import InventoryMode
    from .Utils import *

# Path setup
script_dir = os.path.dirname(os.path.abspath(__file__))

# Default configuration parameters
tolerance = 0.01
json_dir = os.path.join(script_dir, 'JSONHelper', 'Tool_description.json')
csv_dir = os.path.join(script_dir, '..', 'Database')
cutoff = 15
previous_ID = ''
result = {}  # Global storage for experiment results
error_status = {'error_status':'No errors', 'locked':False}  # Tracks experiment errors and lock state
procedures = deque()  # Procedure queue

# Load tool descriptions from JSON configuration
with open(json_dir, "r") as file:
    tool_descriptions = json.load(file)["Experiment_agent"]

# Convert flow rates to µL/s (for precision control)
prime_rate = FLOW_RATE * 1E6
balance_prime_rate = BALANCE_FLOW_RATE * 1E6

# --- Utility Functions ---

def clear_result():
    """Clear the global result dictionary."""
    result.clear()

def set_result(key, value):
    """Set a key-value pair in the global result dictionary."""
    result[key] = value

def get_result():
    """Return the current result dictionary."""
    return result

def get_error_status():
    """Return the current error status message."""
    return error_status['error_status']

def resolve():
    """Reset error status and unlock experiment."""
    error_status['error_status'] = 'No errors'
    error_status['locked'] = False

# Constants for special procedure IDs
WAIT_PROCEDURE = 0
GENERATE_PROCEDURE = -1

@tool(description=tool_descriptions["generate_procedure"])
def generate_procedure():
    """
    Tool entry point for generating and executing experimental procedures.
    Prevents re-run if an error-locked state exists.
    """
    print('Generate_procedure called')
    if error_status['locked']:
        return f'Experiment already runned with error status: {error_status["error_status"]}'
    
    # Extract composition from global result
    composition = result['compositionID'].split('&')
    parts = composition[1]
    composition = composition[0]
    
    # Generate the experiment procedure based on requested measurements
    generate_procedure_helper(composition, density='D' in parts, conductivity='C' in parts, viscosity='V' in parts)

def generate_procedure_helper(composition, density=True, conductivity=True, viscosity=True):
    """
    Build and execute a detailed sequence of instrument procedures for a given composition.
    Each measurement type (density/conductivity/viscosity) is optional.
    """
    if not any([density, conductivity, viscosity]):
        return

    # Define approximate volume based on number of measurements
    volume = (density + conductivity + viscosity) * 0.5 + 1

    # Initialize the main procedure sequence
    procedure_representation = [
        {"id":3, "args":[InventoryMode.SOLVE_LIST], "kwargs":{"target_composition":composition}, "return_keyword":"Mix List"}, 
        {"id":GENERATE_PROCEDURE, "args":["$Mix List"], "kwargs":{}},
        {"id":6, "args":[10], "kwargs":{}}, 
        {"id":4, "args":[1], "kwargs":{}}, 
        {"id":12, "args":[PumpMode.SET_FLOW_RATE, State2.CLOCKWISE, FLOW_RATE, SONICATOR_TUBE_VOLUME * 12], "kwargs":{}}, 
        {"id":11, "args":[3, State_Relay.ON], "kwargs":{}}, 
        {"id":11, "args":[4, State_Relay.ON], "kwargs":{}}, 
        {"id":WAIT_PROCEDURE, "args":[10], "kwargs":{}}, 
        {"id":11, "args":[3, State_Relay.OFF], "kwargs":{}}, 
        {"id":11, "args":[4, State_Relay.OFF], "kwargs":{}}, 
        {"id":WAIT_PROCEDURE, "args":[5], "kwargs":{}}
    ]

    # --- Density measurement sequence ---
    if density:
        density_representation = [
            {"id":10, "args":[1, State_Relay.ON], "kwargs":{}}, 
            {"id":10, "args":[2, State_Relay.ON], "kwargs":{}}, 
            {"id":14, "args":[PumpMode.SET_FLOW_RATE, State2.COUNTER_CLOCKWISE, FLOW_RATE, BALANCE_PRIME_VOLUME], "kwargs":{}}, 
            {"id":9, "args":[], "kwargs":{}, "return_keyword":"First measurement"}, 
            {"id":14, "args":[PumpMode.SET_FLOW_RATE, State2.COUNTER_CLOCKWISE, BALANCE_FLOW_RATE, BALANCE_VOLUME], "kwargs":{}}, 
            {"id":9, "args":[], "kwargs":{}, "return_keyword":"Second measurement"}, 
            {"id":14, "args":[PumpMode.SET_FLOW_RATE, State2.CLOCKWISE, FLOW_RATE, BALANCE_VOLUME * BACK_DIRECTION_FACTOR], "kwargs":{}}, 
            {"id":10, "args":[1, State_Relay.OFF], "kwargs":{}}, 
            {"id":10, "args":[2, State_Relay.OFF], "kwargs":{}}, 
        ]
        procedure_representation += density_representation

    # --- Conductivity measurement sequence ---
    if conductivity:
        conductivity_representation = [
            {"id":10, "args":[3, State_Relay.ON], "kwargs":{}}, 
            {"id":10, "args":[4, State_Relay.ON], "kwargs":{}}, 
            {"id":14, "args":[PumpMode.SET_FLOW_RATE, State2.COUNTER_CLOCKWISE, FLOW_RATE, POTENTIOSTAT_VOLUME], "kwargs":{}}, 
            {"id":8, "args":[], "kwargs":{}, "return_keyword":"Conductivity"}, 
            {"id":14, "args":[PumpMode.SET_FLOW_RATE, State2.CLOCKWISE, FLOW_RATE, POTENTIOSTAT_VOLUME * BACK_DIRECTION_FACTOR], "kwargs":{}}, 
            {"id":10, "args":[3, State_Relay.OFF], "kwargs":{}}, 
            {"id":10, "args":[4, State_Relay.OFF], "kwargs":{}}, 
        ]
        procedure_representation += conductivity_representation

    # --- Viscosity measurement sequence ---
    if viscosity:
        viscosity_representation = [
            {"id":10, "args":[5, State_Relay.ON], "kwargs":{}}, 
            {"id":10, "args":[6, State_Relay.ON], "kwargs":{}}, 
            {"id":14, "args":[PumpMode.SET_FLOW_RATE, State2.COUNTER_CLOCKWISE, FLOW_RATE, VISCOMETER_VOLUME], "kwargs":{}}, 
            {"id":7, "args":[ViscometerMode.START, VISCOMETER_RPM, VISCOSITY_STABLE], "kwargs":{}, "return_keyword":"Viscosity"}, 
            {"id":14, "args":[PumpMode.SET_FLOW_RATE, State2.CLOCKWISE, FLOW_RATE, VISCOMETER_VOLUME * BACK_DIRECTION_FACTOR], "kwargs":{}}, 
            {"id":10, "args":[5, State_Relay.OFF], "kwargs":{}}, 
            {"id":10, "args":[6, State_Relay.OFF], "kwargs":{}}, 
        ]
        procedure_representation += viscosity_representation

    # --- Final steps ---
    procedure_representation += [
        {"id":13, "args":[], "kwargs":{}, "return_keyword":"Temperature"}, 
        {"id":14, "args":[PumpMode.SET_FLOW_RATE, State2.COUNTER_CLOCKWISE, FLOW_RATE, volume], "kwargs":{}}, 
    ]

    # The following block simulates procedure execution sequentially
    context = {}  # Store intermediate outputs (like “Mix List”, “Conductivity”, etc.)
    procedure_representation = deque(procedure_representation)
    try:
        while procedure_representation:
            current = procedure_representation.popleft()

            # Replace variable references like "$Mix List" with actual stored values
            for i in range(len(current["args"])):
                if isinstance(current["args"][i], str) and current["args"][i].startswith("$"):
                    current["args"][i] = context[current["args"][i][1:]]
            for i in current["kwargs"]:
                if isinstance(current["kwargs"][i], str) and current["kwargs"][i].startswith("$"):
                    current["kwargs"][i] = context[current["kwargs"][i][1:]]

            # Create the proper Procedure object based on ID
            if current["id"] == WAIT_PROCEDURE:
                procedure = WaitProcedure(*current["args"])
            elif current["id"] == GENERATE_PROCEDURE:
                procedure = GenerateProcedure(*current["args"])
            else:
                try:
                    # Regular resource-based procedure
                    procedure = ResourceProcedure(resource_map[current["id"]],
                                                  current.get("return_keyword", None),
                                                  10, 0.1,
                                                  *current["args"], **current["kwargs"])
                except KeyError as e:
                    raise KeyError(f"No resource with id={current['id']} found.")
            
            # Run the procedure and collect any returned results
            result = procedure.run() or {}

            # If the procedure dynamically generates more steps, add them to the front
            if current["id"] == GENERATE_PROCEDURE:
                procedure_representation.extendleft(reversed(result))
            else:
                # Store return values in context for later substitution
                context.update(result)
        
        # Mark experiment successful
        error_status["error_status"] = "No errors"
    except Exception as e:
        # Capture and store any runtime error
        error_status["error_status"] = str(e)
    finally:
        # Lock system to prevent re-run until resolved
        error_status['locked'] = True
    
    return error_status["error_status"]
