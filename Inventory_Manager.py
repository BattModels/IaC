import pandas as pd
import numpy as np
import sys
import os
import pulp
import csv
from enum import Enum, auto

# determine current and parent directories for imports / csv paths
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
inventory_directory = os.path.join(current_dir, 'Inventory.csv')
sys.path.insert(0, parent_dir)

# try local imports (useful when running as script) otherwise use package-relative imports
try:
    from Utils import *
    from Relay import State_Relay
    from Resource import Resource, Status
    from Pump import PumpMode, State2
except Exception:
    from .Utils import *
    from .Relay import State_Relay
    from .Resource import Resource, Status
    from .Pump import PumpMode, State2

# Load molar mass lookup tables (CSV files expected to be in same folder)
solvent_molar_mass_table = pd.read_csv(os.path.join(current_dir, 'Solvent Molar mass.csv'))
salt_molar_mass_table = pd.read_csv(os.path.join(current_dir, 'Salt Molar mass.csv'), na_values=[], keep_default_na=False)

# Convert the tables to dicts for fast lookup by name
solvent_molar_mass = {}
for index, row in solvent_molar_mass_table.iterrows():
    solvent_molar_mass[row['Solvent']] = row['Molar_mass']
salt_molar_mass = {}
for index, row in salt_molar_mass_table.iterrows():
    salt_molar_mass[row['Salt']] = row['Molar_mass']

# Column name constants used in code
SOLVENTS = 'Solvent_mass_percentage'
SALTS = 'Salt_molality'

# Modes used by the InventoryManager.action method
class InventoryMode(Enum):
    EDIT_INVENTORY = auto()
    FIND_COMPONENT = auto()
    SOLVE_LIST = auto()

# InventoryManager inherits from Resource (hardware / software resource abstraction)
class InventoryManager(Resource):
    def __init__(self, status, name="Inventory Manager", id=None, inventory_path=None, **attributes):
        # call base constructor (Resource) — expects parent via attributes['parent']
        super().__init__(name=name, id=id, status=status, parent=attributes['parent'])
        # inventory_path can be injected for testing, otherwise default to Inventory.csv in same dir
        self.inventory_path = inventory_path or os.path.join(os.path.dirname(__file__), "Inventory.csv")
        self.inventory = None  # will be a pandas DataFrame after connect()

    # ---------- Abstract Method Implementations ----------
    def connect(self):
        """Load the inventory file into memory and mark the resource as in-use."""
        try:
            self.inventory = pd.read_csv(self.inventory_path)
            self.update_status(Status.IN_USE)
        except Exception as e:
            # propagate failure by marking resource in ERROR state and raising a RuntimeError
            self.update_status(Status.ERROR)
            raise RuntimeError(f"Failed to load inventory: {e}")

    def disconnect(self):
        """Disconnect / cleanup: drop the in-memory inventory and update status."""
        self.inventory = None
        self.update_status(Status.AVAILABLE)

    def action(self, mode, *args, **kwargs):
        """
        Perform an inventory operation based on InventoryMode:
          - FIND_COMPONENT: lookup a composition that meets required volume
          - EDIT_INVENTORY: subtract volume from a port and save CSV
          - SOLVE_LIST: call pulp-based optimizer to compute mixing procedure
        """
        if self.inventory is None:
            # lazy load inventory if needed
            self.connect()
        try:
            if mode == InventoryMode.FIND_COMPONENT:
                # returns a port that holds the requested composition and volume
                port = find_specific_components(kwargs["target_composition"], kwargs["volume"], self.inventory)
                return port

            elif mode == InventoryMode.EDIT_INVENTORY:
                # decrease volume on a given port and persist the CSV file
                if kwargs["port"] not in self.inventory["Port"].values:
                    raise ValueError(f"Port {kwargs['port']} not found in inventory.")

                idx = self.inventory[self.inventory["Port"] == kwargs["port"]].index[0]
                current_volume = float(self.inventory.at[idx, "Volume (mL)"])
                new_volume = max(0.0, current_volume - kwargs["subtract_volume"])

                if new_volume != current_volume:
                    self.inventory.at[idx, "Volume (mL)"] = new_volume
                    self.inventory.to_csv(self.inventory_path, index=False)
                    print(f"[Inventory Updated] Port {port}: {current_volume:.2f} → {new_volume:.2f} mL")
                else:
                    # nothing to subtract (already zero)
                    print(f"[Warning] Port {port} already at 0. No volume subtracted.")
                return new_volume

            elif mode == InventoryMode.SOLVE_LIST:
                # Solve for a set of targets: find which bottles to draw from and produce a
                # representation of the steps (via parameter_list) for the mixing procedure.
                result = pulp_solve_sorted(kwargs["target_composition"], self.inventory, prime=kwargs.get("prime", 0.8), total_volume=kwargs.get("total_volume", 2.5), tolerance=kwargs.get("tolerance", 1E-5))
                result = parameter_list(result)
                return result
        except Exception as e:
            # On any error mark resource as ERROR and re-raise
            self.update_status(Status.ERROR)
            raise e

# Convert pulp solver output into sequence of action dicts understood by the procedure executor
def parameter_list(mix_list):
    result = []
    for current in mix_list:
        # current expected to be [density, index, amount] after sorting from pulp_solve_sorted
        if current[2] > 0:
            # create the sequence of low-level steps (ids correspond to resources/actions)
            result.append({"id":6, "args":[current[1]], "kwargs":{}})
            result.append({"id":10, "args":[7, State_Relay.ON], "kwargs":{}})
            result.append({"id":10, "args":[8, State_Relay.ON], "kwargs":{}})
            result.append({"id":12, "args":[PumpMode.SET_FLOW_RATE, State2.COUNTER_CLOCKWISE, FLOW_RATE, PRIME_VOLUME_VALVE], "kwargs":{}})
            result.append({"id":10, "args":[7, State_Relay.OFF], "kwargs":{}})
            result.append({"id":10, "args":[8, State_Relay.OFF], "kwargs":{}})
            result.append({"id":12, "args":[PumpMode.SET_FLOW_RATE, State2.COUNTER_CLOCKWISE, FLOW_RATE, current[2]], "kwargs":{}})
    return result


def find_specific_components(target_composition, volume, df):
    """
    Find the first row in inventory DataFrame where CompositionID == target_composition
    and Volume (mL) >= required volume. Return the Port column. If none, raise ValueError.
    """
    df = df[df['CompositionID'] == target_composition]
    df = df[df['Volume (mL)'] >= volume]
    try:
        return df.iloc[0]['Port']
    except IndexError:
        raise ValueError(f'Inventory do not have enough composition: {target_composition}')

def solve_list(path="Targets.csv", target='Result.csv'):
    """
    Utility to read a CSV row of target compositions and run pulp_solve for each,
    writing the numeric results into a target CSV file.
    """
    with open(path, mode='r', newline='') as file:
        reader = csv.reader(file)
        compositions = [item for item in next(reader)]
    result = []
    for current in compositions:
        result.append([current] + pulp_solve(current))

    with open(target, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerows(result) 

def pulp_solve_sorted(target_composition, df, prime=0.8, total_volume=2.5, tolerance=10E-6):
    """
    Wrapper: call pulp_solve and then zip results with densities and indices,
    sort by density (useful ordering) and return the sorted list of tuples.
    """
    result = pulp_solve(target_composition, df, salt_molar_mass_table, prime, total_volume, tolerance)
    zipped = zip(df['Density (g/mL)'], range(len(result)), result)
    zipped = sorted(zipped, key=lambda x: x[0])
    return list(zipped)


def pulp_solve(target_composition, df=pd.read_csv(inventory_directory), molar_mass = salt_molar_mass_table, prime=0.8, total_volume=2.5, tolerance=10E-6):
    """
    Core optimization routine using pulp:
      - Build linear / mixed-integer problem to select bottles and amounts
      - Objective: minimize total amount used + priming penalty (weights)
      - Constraints: composition equality (solvent ratios, salt mass balance), inventory bounds, and indicator constraints
      - Returns an array of volumes (converted from mass via density)
    """
    constraints = generate_constraints(df, dict(zip(molar_mass['Salt'], molar_mass['Molar_mass'])), target_composition, total_volume, prime)
    # Create a MIP problem
    prob = pulp.LpProblem("Minimize_Bottles_With_Priming_And_Continuous", pulp.LpMinimize)

    # Binary variable per bottle indicating whether the bottle is used at all
    bottle_vars = [pulp.LpVariable(f"bottle_{i}_used", cat="Binary") for i in range(len(df))]

    # Continuous variables for the amount drawn from each bottle (bounded by Upper_bounds)
    amount_vars = [pulp.LpVariable(f"bottle_{i}_amount", lowBound=0, upBound=constraints["Upper_bounds"][i]) for i in range(min(len(df), len(constraints["Upper_bounds"])))]

    # weights used in objective to penalize using many bottles and the priming waste
    weights = prime * df['Density (g/mL)']

    # Objective function: total drawn volume + priming penalty per used bottle
    prob += pulp.lpSum(amount_vars) + pulp.lpSum(weights[i] * bottle_vars[i] for i in range(len(weights))), "Objective"

    # Add equality constraints (with small tolerance band) built in generate_constraints
    for i, constraint, target in zip(range(len(constraints["Equal_constraints"])), constraints["Equal_constraints"], constraints["Equal_targets"]):
        prob += pulp.lpSum(constraint[j] * amount_vars[j] for j in range(len(constraint))) >= target - tolerance, f"Constraint_sum_lower{i}"
        prob += pulp.lpSum(constraint[j] * amount_vars[j] for j in range(len(constraint))) <= target + tolerance, f"Constraint_sum_upper{i}"

    # Link amount_vars with bottle_vars: if bottle_vars[i] == 0 then amount_vars[i] == 0
    for i in range(min(len(df), len(constraints["Upper_bounds"]))):
        prob += amount_vars[i] <= bottle_vars[i] * constraints["Upper_bounds"][i], f"Indicator_constraint_{i}"

    # Solve the problem using CBC (silent)
    result = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if result == -1:
        # solver failure: treat as runtime error (insufficient inventory)
        raise RuntimeError("Low inventory, cannot make enough desired solution.")
    # return amounts expressed as volumes (amount vars are mass; divide by density)
    return np.array([pulp.value(current) for current in amount_vars]) / df['Density (g/mL)']


def generate_constraints(df, molar_mass, target_id, total_volume, prime_volume):
    """
    Build the linear constraints matrices required by pulp_solve:
      - Parse each inventory composition into solvent mass percentages and salt molalities
      - Build per-component coefficients for equality constraints and the equal_targets
      - Add density-volume equality and upper bound constraints (inventory - prime volume)
      - Returns dict with Equal_constraints, Equal_targets, bounds, Lower_bounds, Upper_bounds
    """
    # parse composition strings in inventory into structured columns
    df[[SOLVENTS, SALTS]] = df['CompositionID'].apply(parse_helper).apply(pd.Series)
    verifyCompositionIDInside(target_id)
    salt_mass_ratios = {}
    equal_constraints = []
    equal_targets = []
    solvents = {}
    salts = {}

    # Iterate through each inventory row to collect solvent and salt coefficient vectors
    for i, row in df.iterrows():
        sum_salt_mass = 0
        for s, m in zip(row[SALTS]['salt'], row[SALTS]['molality']):
            # accumulate salt mass (molar_mass * molality)
            sum_salt_mass += molar_mass[s] * m
            # initialize arrays for each salt encountered
            if s not in salts:
                salts[s] = np.zeros(len(df))
            if s not in salt_mass_ratios:
                salt_mass_ratios[s] = np.zeros(len(df))
            salts[s][i] = m
            # salt_mass_ratios stores fraction: salt_mass / (1000 + salt_mass)
            salt_mass_ratios[s][i] = (sum_salt_mass / (1000 + sum_salt_mass))
        for s, p in zip(row[SOLVENTS]['solvent'], row[SOLVENTS]['mass_percentage']):
            if s not in solvents:
                solvents[s] = np.zeros(len(df))
            # solvents stored as fraction (percentage / 100)
            solvents[s][i] = p / 100

    # parse the target composition (the one we want to make)
    target_components = verifyCompositionID('', target_id)
    # compute total salt mass ratio across all salts for each inventory row
    salt_mass_ratio_total = np.zeros(len(df))
    for salt in salt_mass_ratios:
        salt_mass_ratio_total += salt_mass_ratios[salt]
    try:
        # For each solvent requested in target, build a constraint to match mass percentages
        for solvent, percentage in zip(target_components['Solvent_mass_percentage']['solvent'], target_components['Solvent_mass_percentage']['mass_percentage']):
            coefficients = (percentage / 100 - solvents[solvent]) * (1 - salt_mass_ratio_total)
            equal_constraints.append(coefficients)
            equal_targets.append(0)
        # Ensure salts that exist in inventory but not in target are appended with molality 0
        for salt in salts:
            if salt != 'None' and salt not in target_components['Salt_molality']['salt']:
                target_components['Salt_molality']['salt'].append(salt)
                target_components['Salt_molality']['molality'].append(0)
        # For each salt requested in target, build salt-mass balance constraints
        for salt, molality in zip(target_components['Salt_molality']['salt'], target_components['Salt_molality']['molality']):
            if salt != 'None':
                coefficients = molality / 1000 * (1 - salt_mass_ratios[salt]) - salt_mass_ratios[salt] / molar_mass[salt]
                equal_constraints.append(coefficients)
                equal_targets.append(0)
    except KeyError as e:
        # If parsing failed (target missing components), return a degenerate constraint set to cause failure upstream
        print(str(e))
        return {"Equal_constraints":np.zeros((1, 1)), "Equal_targets":np.array([1]), "bounds":np.array([(0, 0)]), "Lower_bounds":np.array([0]), "Upper_bounds":np.array([0])}
    
    # density constraint: 1/density * amount_vars sums to total_volume (mass/density = volume)
    density = df['Density (g/mL)'].to_numpy()
    equal_constraints.append(1 / density)
    equal_targets.append(total_volume)

    # Upper bounds: available volume minus prime_volume (can't draw prime volume)
    upper_bounds = df['Volume (mL)'].to_numpy() - prime_volume
    upper_bounds = np.where(upper_bounds < 0, 0, upper_bounds)
    bounds = [(x, y) for x, y in zip(np.zeros(len(upper_bounds)), np.ones(len(upper_bounds)) * total_volume)]
    return {"Equal_constraints":np.vstack(equal_constraints), "Equal_targets":equal_targets, "bounds":bounds, "Lower_bounds":np.zeros(len(upper_bounds)), "Upper_bounds":upper_bounds}

def verifyCompositionIDInside(val):
    """
    Wrapper for verifyCompositionID used internally.
    Returns parsed composition dict (or error string) — kept for compatibility with other code.
    """
    result = verifyCompositionID('', val)
    '''
    if isinstance(result, str):
        return result
    if result[SALTS]['salt'][0] == 'None':
        result[SALTS]['salt'] = []
        result[SALTS]['molality'] = []
    '''
    return result

def parse_helper(val):
    """
    parse_helper is applied to each inventory 'CompositionID' to produce two pandas Series:
      - first: Solvent_mass_percentage dict series
      - second: Salt_molality dict series
    This allows .apply(pd.Series) to create two DataFrame columns.
    """
    result = verifyCompositionIDInside(val)
    return pd.Series(result[SOLVENTS]), pd.Series(result[SALTS])

def verifyCompositionID(property, str):
    """
    Validate and parse a composition ID string of the form:
      solvent1_solvent2|p1_p2|salt1_salt2|m1_m2

    Returns structured dict with:
      - Solvent_mass_percentage: {'solvent': [...], 'mass_percentage': [...]}
      - Salt_molality: {'salt': [...], 'molality': [...]}
      - Solvent_molar_ratio and Salt_molar_ratio computed via molar masses
    Or returns an error string describing the problem.
    """
    # Check compositionID
    error_comp_id = 'Please enter a valid composition ID.'
    if str==None:
        return error_comp_id
    splitted_string = str.split('|')
    if len(splitted_string) != 4:
        return error_comp_id
    solvents = splitted_string[0].split('_')
    percentage = splitted_string[1].split('_')
    if len(solvents) != len(percentage):
        return error_comp_id
    
    molar_ratio = []
    for i in range(len(percentage)):
        if solvents[i] not in solvent_molar_mass:
            return f"No solvents named {solvents[i]} is found."
        try:
            percentage[i] = float(percentage[i])
        except ValueError:
            return error_comp_id
        if percentage[i] <= 0:
            return error_comp_id
        molar_ratio.append(percentage[i] / solvent_molar_mass[solvents[i]])
    # Ensure solvent percentages sum to 100 (strict floating tolerance)
    if abs(sum(percentage) - 100) > 1E-10:
           return 'Percentages of solvents must sum up to 100.'
    salts = splitted_string[2].split('_')
    molality = splitted_string[3].split('_')
    if len(salts) != len(molality):
        return error_comp_id
    for i in range(len(molality)):
        if salts[i] not in salt_molar_mass:
            return f"No salts named {salts[i]} is found."
        molar_ratio.append(float(molality[i]) / 10)
        try:
            molality[i] = float(molality[i])
        except ValueError:
            return error_comp_id
        if salts[i] != 'None' and molality[i] <= 0:
            return error_comp_id
    
    # Normalize molar ratio arrays to sum to 1 and split into solvent/salt parts
    molar_ratio = np.array(molar_ratio) / sum(molar_ratio)
    return {
        'Solvent_mass_percentage': {'solvent':solvents, 'mass_percentage':percentage},
        'Salt_molality': {'salt':salts, 'molality':molality}, 
        'Solvent_molar_ratio':{'solvent':solvents, 'molar_ratio':molar_ratio[0:len(solvents)]},
        'Salt_molar_ratio':{'salt':salts, 'molar_ratio':molar_ratio[len(solvents):]}
    }
