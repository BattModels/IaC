import numpy as np
from itertools import product
from langchain_core.tools import tool
import json
import os
import pandas as pd
from datetime import datetime
import random
import math
import sys
import csv
import multiprocessing
from collections import Counter
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from Inventory_Manager import pulp_solve_sorted, inventory_directory
from Utils import *

script_dir = os.path.dirname(os.path.abspath(__file__))
tolerance = 0.01
json_dir = os.path.join(script_dir, 'JSONHelper', 'Tool_description.json')
csv_dir = script_dir
cutoff = 3

solvent_elements = []
solvent_max = []
solvent_min = []
salt_elements = []
salt_max = []
salt_min = []

with open(json_dir, "r") as file:
    tool_descriptions = json.load(file)["Front_agent"]

solvent_molar_mass_table = pd.read_csv(os.path.join(csv_dir, 'Solvent Molar mass.csv'))
salt_molar_mass_table = pd.read_csv(os.path.join(csv_dir, 'Salt Molar mass.csv'))
solvent_molar_mass = {}
for index, row in solvent_molar_mass_table.iterrows():
    solvent_molar_mass[row['Solvent']] = row['Molar_mass']
salt_molar_mass = {}
for index, row in salt_molar_mass_table.iterrows():
    salt_molar_mass[row['Salt']] = row['Molar_mass']

@tool(description=tool_descriptions["Generate_space_sum"])
def generate_space_sum(elements: list, minimum: list, maximum: list, steps: list, total=100):
    global solvent_elements, solvent_max, solvent_min
    solvent_elements = elements
    solvent_max = maximum
    solvent_min = minimum
    def helper(elements, minimum, maximum, steps, total, i):
        if total < -tolerance:
            return [], []
        if i <= 0:
            
            if minimum[0] - total > tolerance or total - maximum[0] > tolerance:
                return [], []
            if abs(total) < tolerance:
                return [[]], [[]]
            return [[elements[0]]], [[total]]
        
        result_elements = []
        result_values = []
        max_value = min(maximum[i], total)
        if steps[i] < 2 or abs(max_value - minimum[i]) < tolerance:
            j_range = [minimum[i]]
        else:
            j_range = np.arange(minimum[i], max_value + tolerance, (maximum[i] - minimum[i]) / max(1, (steps[i] - 1)))
        for j in j_range:
            temp_elements, temp_values = helper(elements, minimum, maximum, steps, total-j, i - 1)
            if temp_values is None:
                return temp_elements, temp_values 
            for temp_element, temp_value in zip(temp_elements, temp_values):
                if j > tolerance:
                    result_elements.append(temp_element + [elements[i]])
                    result_values.append(temp_value + [j])
                else:
                    result_elements.append(temp_element)
                    result_values.append(temp_value)
            if len(result_elements) > 100:
                return 'Too many combinations. Please use hit_and_run instead'
        return result_elements, result_values
    print('Solvent agent')
    result_elements, result_values = helper(elements, minimum, maximum, steps, total, len(elements) - 1)
    return result_elements, result_values
'''
@tool(description=tool_descriptions["Generate_space_grid"])
def generate_space_grid(elements, minimum, maximum, steps=1):
    global salt_elements, salt_max, salt_min
    salt_elements = elements
    salt_max = maximum
    salt_min = minimum
    if not isinstance(elements, list):
        elements = [elements]
    if not isinstance(minimum, list):
        minimum = [minimum]
    if not isinstance(maximum, list):
        maximum = [maximum]
    if not isinstance(steps, list):
        steps = [steps]
    ranges = [
        np.linspace(min_val, max_val, step)
        for min_val, max_val, step in zip(minimum, maximum, steps)
    ]
    grid = list(product(*ranges))

    result = np.tile(elements, (len(grid), 1)).tolist()
    for i in range(len(result)):
        filtered = [(s, v) for s, v in zip(result[i], grid[i]) if abs(v) > tolerance]
        result[i], grid[i] = zip(*filtered) if filtered else ([], [])
    print('Salt agent')
    return result, grid'''

@tool(description=tool_descriptions["Generate_space_grid"])
def random_space_grid(elements, minimum, maximum, points=1):
    global salt_elements, salt_max, salt_min
    salt_elements = elements
    salt_max = maximum
    salt_min = minimum
    if not isinstance(elements, list):
        elements = [elements]
    if not isinstance(minimum, list):
        minimum = [minimum]
    if not isinstance(maximum, list):
        maximum = [maximum]
    grid = []
    for i in range(points):
        sample = []
        for mi, ma in zip(minimum, maximum):
            sample.append(np.random.uniform(mi, ma))
        grid.append(tuple(sample))

    result = np.tile(elements, (len(grid), 1)).tolist()
    for i in range(len(result)):
        filtered = [(s, v) for s, v in zip(result[i], grid[i]) if abs(v) > tolerance]
        result[i], grid[i] = zip(*filtered) if filtered else ([], [])
    print('Salt agent')
    return result, grid

def verify_space_helper(elements, values, state, solvent=True):
    state['verified'] = False
    element_ph = 'solvent' if solvent else 'salt'
    value_ph = 'mass percentage' if solvent else 'molality'
    exist_table = solvent_molar_mass if solvent else salt_molar_mass

    if len(elements) != len(values):
        return f'Number of {element_ph} lists does not match the number of corresponding {value_ph} list. You applied generate_space_grid incorrectly.'
    for element, value in zip(elements, values):
        result = ''
        if len(element) != len(value):
            result = f'For this combination {element}, {value}, number of {element_ph}s does not match its respective {value_ph}. You applied generate_space_grid incorrectly.'
        else:
            repeats = repeated_list(element)
            if repeats:
                return f'Your generated ID has repeated elements: {repeats}. Please get rid of the repeats and regenerate.'
            for current_element, current_value in zip(element, value):
                if len(current_element) == 1:
                    result = f'The {element_ph} names have at least two letters. For a single {element_ph}, you should not separate it into three characters (For example, {element_ph} name is AAA, you should not separate it into ["A", "A", "A"]).'
                try:
                    float(current_value)
                except ValueError:
                    result = f'The {value_ph} section with values {value} cannot have non-numeric values: {current_value}.'
                if current_element not in exist_table:
                    result = f'The {element_ph}s in {element} contains {current_element} that doesn\'t exist.'
                if solvent and abs(sum(value) - 100) > tolerance:
                    result = f'The {value_ph}s in {value} needs to sum up to 100.'
        if result:
            print(f'The {element_ph}: {element}, {value} failed evaluation')
            return result
    print(f'All {element_ph} passed verification')
    state['verified'] = True
    return 'All experiments correctly generated. Proceed to next step.'
            
def generate_ID(elements, values):
    try:
        elements = np.array(elements)
            
        if elements.ndim < 2 and len(elements) < len(values):
            elements = np.tile(elements, (len(values), 1)).tolist()
            if len(values) > 1:
                values = np.array(values)
                values = values.reshape(-1, 1)
            else:
                values = np.tile(values, (len(values), 1)).tolist()
    except Exception as e:
        pass
    
    try:
        result = []
        for element, value in zip(elements, values):
            if len(element) == 0 or value == 0:
                result.append('None|0')
            else:
                element = ensure_list(element)
                value = ensure_list(value)
                if len(element) != len(value) and len(element) == 1:
                    element = element * len(value)
                result.append('_'.join(element) + '|' + '_'.join(str(n) for n in value))
    except Exception as e:
        raise(e)
    return result
    

def merge_ID(id_list1, id_list2):
    random.shuffle(id_list1)
    random.shuffle(id_list2)
    if len(id_list2) <= 0:
        id_list2 = ["None|0"]
    try:
        if len(id_list1) < cutoff:
            multiple_factor = math.ceil(len(id_list2) / len(id_list1))
            id_list1 = id_list1 * multiple_factor
        else:
            multiple_factor = math.ceil(len(id_list1) / len(id_list2))
            id_list2 = id_list2 * multiple_factor
        result = []
        i = 0
        for i in range(len(id_list1)):
            current = id_list1[i]
            current2 = id_list2[i]
            result.append(current + '|' + current2)
            i += 1
        print('Finished Merging')
        return result
    except Exception as e:
        print(e)
        return 'Error'

def ensure_list(x):
    if isinstance(x, str) or isinstance(x, np.str_):
        return [x]
    elif isinstance(x, dict):
        return list(x.keys())
    try:
        a = x[0]
        return list(x)
    except Exception as e:
        return [x]
    

@tool(description=tool_descriptions["Generate_compositionID"] + tool_descriptions["Verify_CompositionID"])
def generate_ID_list_filename(solvents, percentages, salts, molalities, file_name, density, conductivity, viscosity, repeat=1):
    return generate_ID_list(solvents, percentages, salts, molalities, file_name, density, conductivity, viscosity, repeat)

@tool(description=tool_descriptions["Generate_compositionID"] + tool_descriptions["Verify_CompositionID"])
def generate_ID_list_no_filename(solvents, percentages, salts, molalities, density, conductivity, viscosity, repeat=1):
    return generate_ID_list(solvents, percentages, salts, molalities, file_name=None, density=density, conductivity=conductivity, viscosity=viscosity, repeat=repeat)

def generate_ID_list(solvents, percentages, salts, molalities, file_name=None, density=True, conductivity=True, viscosity=True, repeat=2):
    list1 = generate_ID(solvents, percentages)
    list2 = generate_ID(salts, molalities)
    result = merge_ID(list1, list2)
    result = [item for item in result for _ in range(repeat)]
    print(result)

    global solvent_elements, solvent_max, solvent_min, salt_elements, salt_max, salt_min
    ids = result
    try:
        
        correct = 'No IDs'
        for current in ids:
            result = verifyCompositionID(current)
            if isinstance(result, str):
                if 'correct':
                    correct = f'The compositionID {correct} is a correctly generated one. You should make reference to it.'
                return f'Error at token: {current}, {result}. {correct} This is likely due to you parsed solvents and salts in a wrong way. Please use generate_ID_list and pass in the arguments in a different way.'
            correct = current
        print('All ids are correctly generated.')
        feasible, infeasible = get_feasible_and_ifeasible_items(ids)
        session = {}
        prev_file_name = file_name
        if not file_name or not os.path.exists(file_name):
            current_time = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
            file_name = f"{current_time}.json"
            
            session['solvents'] = ensure_list(solvent_elements)
            session['solvent_max'] = ensure_list(solvent_max)
            session['solvent_min'] = ensure_list(solvent_min)
            session['salts'] = ensure_list(salt_elements)
            session['salt_max'] = ensure_list(salt_max)
            session['salt_min'] = ensure_list(salt_min)
            session['results'] = []
        else:
            with open(file_name, "r") as f:
                session = json.load(f)

        appendix = "&"
        if density:
            appendix += "D"
        if conductivity:
            appendix += "C"
        if viscosity:
            appendix += "V"
        for i in range(len(feasible)):
            feasible[i] = feasible[i] + appendix
        session['experiments'] = dict(Counter(feasible))
        with open(os.path.join(script_dir, 'Generated JSON', file_name), mode="w") as file:
            json.dump(session, file, indent=4)
        return {'file_name':file_name, 'infeasible experiments':infeasible, 'messages':f'Good. Please file_name is no longer {prev_file_name}, it is now {file_name}. You can start experiments when instructed.'}
    except Exception as e:
        print(e)
        return f"This encounters an error: {str(e)}, did you pass in a list of strings instead of a list of dict-type object?"


def verifyCompositionID(str):
    # Check compositionID
    if str==None:
        return 'The string cannot be empty'
    splitted_string = str.split('|')
    if len(splitted_string) != 4:
        return 'The ID should have 4 sections, each separated by character \'|\''
    solvents = splitted_string[0].split('_')
    percentage = splitted_string[1].split('_')
    salts = splitted_string[2].split('_')
    molality = splitted_string[3].split('_')
    repeated_list_solvents = repeated_list(solvents)
    if repeated_list_solvents:
        return f'The ID {str} you generated contains repeated solvents. Here are the solvents: {repeated_list_solvents}. The correct id should be {repeated_list_solvents}|{percentage[:len(repeated_list_solvents)]}|(salts)|(molalities). Please regenerate and make sure all the solvents appear in the list at most once.'
    
    repeated_list_salts = repeated_list(salts)
    if repeated_list_salts:
        return f'The ID {str} you generated contains repeated salts. Here are the solvents: {repeated_list_salts}. The correct id should be (solvents)|(percentagess)|{repeated_list_salts}|{percentage[:len(molality)]}. Please regenerate and make sure all the salts appear in the list at most once.'
    if len(solvents) != len(percentage):
        return 'The number of solvents should match the number of percentages. Please use generate_space_sum or hit_and_run to regenerate the design space.'
    
    molar_ratio = []
    for i in range(len(percentage)):
        if solvents[i] not in solvent_molar_mass:
            if len(solvents[i]) == 1:
                return f"The solvent names have at least two letters. For a single solvent, you should not use _ to separate the characters. If there is a single solvent is called AAA, you should put AAA|100 instead of A_A_A|(mass percentage of A)_(mass percentage of A)_(mass percentage of A)"
            return f"No solvents named {solvents[i]} is found. Please check your parsing."
        try:
            percentage[i] = float(percentage[i])
        except ValueError:
            return "The second section should have the respective mass percentage of solvents, not solvent names."
        if percentage[i] < 0:
            return f"Percentage mass of {solvents[i]} cannot be negative."
        elif percentage[i] == 0:
            return f"You should omit solvent {solvents[i]} if its mass percentage is zero."
        molar_ratio.append(percentage[i] / solvent_molar_mass[solvents[i]])
    if abs(sum(percentage) - 100) > tolerance:
           return 'Percentages of solvents must sum up to 100.'
    
    if len(salts) != len(molality):
        return 'The number of salts should match the number of molalities. Please use generate_space_grid to regenerate the design space.'
    for i in range(len(molality)):
        if salts[i] != 'None' and salts[i] not in salt_molar_mass:
            return f"No salts named {salts[i]} is found. Please check your parsing."
        if salts[i] != 'None' and float(molality[i]) == 0:
            return f"You can omit salt {salts[i]} if its molality is zero. If every type of salt has zero molality, you should put |None|0 in the end as a placeholder instead of |{salts[i]}|0.0."
        molar_ratio.append(float(molality[i]) / 10)
    
    molar_ratio = np.array(molar_ratio) / sum(molar_ratio)
    
    return {'Solvent_mass_percentage': {'solvent':solvents, 'mass_percentage':percentage}, 'Salt_molality': {'salt':salts, 'molality':molality}, 
    'Solvent_molar_ratio':{'solvent':solvents, 'molar_ratio':molar_ratio[0:len(solvents)]},
    'Salt_molar_ratio':{'salt':salts, 'molar_ratio':molar_ratio[len(solvents):]}}

@tool(description=tool_descriptions["Generate_sum_hit_and_run"])
def hit_and_run(elements: list, minimum: list, maximum: list, num_samples, burn_in=1000):
    print('Hit and run')
    minimum = np.array(minimum) / 100
    maximum = np.array(maximum) / 100

    def project(x0, d):
        # Find bounds for alpha such that x0 + alpha * d stays in bounds
        alpha_min, alpha_max = -np.inf, np.inf
        for i in range(len(elements)):
            if d[i] != 0:
                a1 = (minimum[i] - x0[i]) / d[i]
                a2 = (maximum[i] - x0[i]) / d[i]
                amin = min(a1, a2)
                amax = max(a1, a2)
                alpha_min = max(alpha_min, amin)
                alpha_max = min(alpha_max, amax)
        return alpha_min, alpha_max


    x = minimum.copy()
    remain = 1 - np.sum(x)
    for i in range(x.shape[0]):
        if x[i] + remain < maximum[i]:
            x[i] += remain
        else:
            remain -= maximum[i] - minimum[i]
            x[i] = maximum[i]
    samples = []
    total_steps = burn_in + num_samples

    for step in range(total_steps):
        # Sample a random direction with zero-sum (to stay on the sum-1 hyperplane)
        d = np.random.randn(len(elements))
        d -= np.mean(d)  # ensure sum(d) = 0, so x + alpha*d stays in simplex
        alpha_min, alpha_max = project(x, d)
        alpha = np.random.uniform(alpha_min, alpha_max)
        x_new = x + alpha * d
        x = x_new

        if step >= burn_in:
            samples.append(x.copy() * 100)
    result = np.tile(elements, (num_samples, 1)).tolist()
    return result, np.array(samples)

@tool(description=tool_descriptions["Start_experiment"])
def run_experiment(file_name):
    file_path = os.path.join(script_dir, 'Generated JSON', file_name)
    '''
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            compositionID.extend(row)  # Flatten all cells into one list
    if isinstance(compositionID, str):
        compositionID = [compositionID]
    for current in compositionID:
        current_id = current
        while isinstance(current_id, list):
            current_id = current_id[0]
        verify_result = verifyCompositionID(current_id)
        if isinstance(verify_result, str):
            print(f"The compositionID {compositionID} is incorrect. Reason: {verify_result} Please first look for the correct ones and then run experiment again.")
            return f"The compositionID {compositionID} is incorrect. Reason: {verify_result} Please first look for the correct ones and then run experiment again."'''
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
        experiments = list(Counter(data['experiments']).elements())
        return {"experiment_list": experiments, "file_name":file_name}
    except Exception as e:
        return 'The experiment list file has name with YYYY-MM-DD HH-MM-SS.json. What is the most recent one in your memory?'

@tool(description=tool_descriptions["Continue_experiment"])
def continue_experiment():
    return {"continue": True}

@tool(description=tool_descriptions["Get_experiment_progress"])
def get_experiment_progress():
    return {"progress": True}

def get_feasible_and_ifeasible_items(compositionID):
    inventory_df = pd.read_csv(inventory_directory)
    feasible_items = []
    infeasible_items = []
    for current in compositionID:
        try:
            result = pulp_solve_sorted(current, df=inventory_df)
            for current_bottle in result:
                if current_bottle[2] > 0 and inventory_df.iloc[current_bottle[1], 3] - PRIME_VOLUME_VALVE < current_bottle[2]:
                    inventory_df.iloc[current_bottle[1], 3] = inventory_df.iloc[current_bottle[1], 3] - PRIME_VOLUME_VALVE - current_bottle[2]
            feasible_items.append(current)
        except Exception as e:
            infeasible_items.append(current)
    return feasible_items, infeasible_items

def repeated_list(lst):
    counts = Counter(lst)
    return [item for item, count in counts.items() if count > 1].sort()