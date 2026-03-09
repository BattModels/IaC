import pandas as pd
import numpy as np
import sys
import os
import pulp
import csv
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
inventory_directory = os.path.join(current_dir, 'Inventory.csv')
sys.path.insert(0, parent_dir)
SOLVENTS = 'Solvent_mass_percentage'
SALTS = 'Salt_molality'

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

def find_specific_components(target_composition, volume):
    df = pd.read_csv(inventory_directory)
    df = df[df['CompositionID'] == target_composition]
    df = df[df['Volume (mL)'] >= volume]
    try:
        return df.iloc[0]['Port']
    except IndexError:
        raise ValueError(f'Inventory do not have enough composition: {target_composition}')

def solve_list(path="Targets.csv", target='Result.csv'):
    with open(path, mode='r', newline='') as file:
        reader = csv.reader(file)
        compositions = [item for item in next(reader)]
    result = []
    for current in compositions:
        result.append([current] + pulp_solve(current))

    with open(target, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerows(result) 

def pulp_solve_sorted(target_composition, df=None, molar_mass = salt_molar_mass_table, prime=0.8, total_volume=2.5, tolerance=10E-6):
    if df is None:
        df=pd.read_csv(inventory_directory)
    result = pulp_solve(target_composition, df, molar_mass, prime, total_volume, tolerance)
    zipped = zip(df['Density (g/mL)'], range(len(result)), result)
    zipped = sorted(zipped, key=lambda x: x[0])
    return list(zipped)


def pulp_solve(target_composition, df=pd.read_csv(inventory_directory), molar_mass = salt_molar_mass_table, prime=0.8, total_volume=2.5, tolerance=10E-6):
    constraints = generate_constraints(df, dict(zip(molar_mass['Salt'], molar_mass['Molar_mass'])), target_composition, total_volume, prime)
    # Create a MIP problem
    prob = pulp.LpProblem("Minimize_Bottles_With_Priming_And_Continuous", pulp.LpMinimize)

    # Create binary decision variables for each bottle (0 = don't use, 1 = use)
    bottle_vars = [pulp.LpVariable(f"bottle_{i}_used", cat="Binary") for i in range(len(df))]

    # Create continuous decision variables for the amount of solvent used from each bottle
    amount_vars = [pulp.LpVariable(f"bottle_{i}_amount", lowBound=0, upBound=constraints["Upper_bounds"][i]) for i in range(min(len(df), len(constraints["Upper_bounds"])))]

    weights = prime * df['Density (g/mL)']

    # Objective function: Minimize total volume including priming waste
    prob += pulp.lpSum(amount_vars) + pulp.lpSum(weights[i] * bottle_vars[i] for i in range(len(weights))), "Objective"
    # Constraints in ration and inventory
    for i, constraint, target in zip(range(len(constraints["Equal_constraints"])), constraints["Equal_constraints"], constraints["Equal_targets"]):
        prob += pulp.lpSum(constraint[j] * amount_vars[j] for j in range(len(constraint))) >= target - tolerance, f"Constraint_sum_lower{i}"
        prob += pulp.lpSum(constraint[j] * amount_vars[j] for j in range(len(constraint))) <= target + tolerance, f"Constraint_sum_upper{i}"
    for i in range(min(len(df), len(constraints["Upper_bounds"]))):
        prob += amount_vars[i] <= bottle_vars[i] * constraints["Upper_bounds"][i], f"Indicator_constraint_{i}"
    # Solve the problem
    result = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if result == -1:
        raise RuntimeError("Low inventory, cannot make enough desired solution.")
    return np.array([pulp.value(current) for current in amount_vars]) / df['Density (g/mL)']

def generate_constraints(df, molar_mass, target_id, total_volume, prime_volume):
    df[[SOLVENTS, SALTS]] = df['CompositionID'].apply(parse_helper).apply(pd.Series)
    verifyCompositionIDInside(target_id)
    salt_mass_ratios = {}
    equal_constraints = []
    equal_targets = []
    solvents = {}
    salts = {}

    for i, row in df.iterrows():
        sum_salt_mass = 0
        for s, m in zip(row[SALTS]['salt'], row[SALTS]['molality']):
            
            sum_salt_mass += molar_mass[s] * m
            if s not in salts:
                salts[s] = np.zeros(len(df))
            if s not in salt_mass_ratios:
                salt_mass_ratios[s] = np.zeros(len(df))
            salts[s][i] = m
            salt_mass_ratios[s][i] = (sum_salt_mass / (1000 + sum_salt_mass))
        for s, p in zip(row[SOLVENTS]['solvent'], row[SOLVENTS]['mass_percentage']):
            if s not in solvents:
                solvents[s] = np.zeros(len(df))
            solvents[s][i] = p / 100


    target_components = verifyCompositionID('', target_id)
    salt_mass_ratio_total = np.zeros(len(df))
    for salt in salt_mass_ratios:
        salt_mass_ratio_total += salt_mass_ratios[salt]
    try:
        for solvent, percentage in zip(target_components['Solvent_mass_percentage']['solvent'], target_components['Solvent_mass_percentage']['mass_percentage']):
            coefficients = (percentage / 100 - solvents[solvent]) * (1 - salt_mass_ratio_total)
            equal_constraints.append(coefficients)
            equal_targets.append(0)
        #equal_constraints = equal_constraints[:-1]
        #equal_targets = equal_targets[:-1]
        
        for salt in salts:
            if salt != 'None' and salt not in target_components['Salt_molality']['salt']:
                target_components['Salt_molality']['salt'].append(salt)
                target_components['Salt_molality']['molality'].append(0)
        for salt, molality in zip(target_components['Salt_molality']['salt'], target_components['Salt_molality']['molality']):
            
            if salt != 'None':
                coefficients = molality / 1000 * (1 - salt_mass_ratios[salt]) - salt_mass_ratios[salt] / molar_mass[salt]
                equal_constraints.append(coefficients)
                equal_targets.append(0)
    except KeyError as e:
        print(str(e))
        return {"Equal_constraints":np.zeros((1, 1)), "Equal_targets":np.array([1]), "bounds":np.array([(0, 0)]), "Lower_bounds":np.array([0]), "Upper_bounds":np.array([0])}
    
    density = df['Density (g/mL)'].to_numpy()
    equal_constraints.append(1 / density)
    equal_targets.append(total_volume)

    upper_bounds = df['Volume (mL)'].to_numpy() - prime_volume
    upper_bounds = np.where(upper_bounds < 0, 0, upper_bounds)
    bounds = [(x, y) for x, y in zip(np.zeros(len(upper_bounds)), np.ones(len(upper_bounds)) * total_volume)]
    return {"Equal_constraints":np.vstack(equal_constraints), "Equal_targets":equal_targets, "bounds":bounds, "Lower_bounds":np.zeros(len(upper_bounds)), "Upper_bounds":upper_bounds}

def verifyCompositionIDInside(val):
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

if __name__ == '__main__':
    print(pulp_solve_sorted('H2O|100|NaNO3|8.44616983353725'))