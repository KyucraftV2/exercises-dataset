from a import *

frenchexo = get_lang("fr")

list_equipment = []
for exercise in data_exercises:
    for k,v in exercise.items():
        if k == 'equipment':
            if v not in list_equipment:
                list_equipment.append(v)
