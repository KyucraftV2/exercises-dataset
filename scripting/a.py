import json

with open('../data/exercises.json') as f:
    data_exercises:list[dict] = json.load(f)

with open('../data/exercises.schema.json') as f:
    schema_exercises:dict = json.load(f)

def get_lang(lang:str)->list[dict]:
    instruction_only_language:list[dict] = []
    for exercise in data_exercises:
        new_exercise:dict[str,str] = {}
        for k,v in exercise.items():
            if k == "instructions" or k=="instruction_steps":
                new_exercise[k] = v[(lang)]
            else:
                new_exercise[k] = v
        instruction_only_language.append(new_exercise)

    return instruction_only_language

def get_exercise(exercises:list[dict],equipments:list[str])->list[dict]:
    exercise_filtered:list[dict] = []
    for exercise in exercises:
        if exercise["equipment"] in equipments:
            exercise_filtered.append(exercise)
    return exercise_filtered

def get_exercise_from_muscle_group(exercises:list[dict],muscle_group:list[str])->list[dict]:
    exercise_filtered:list[dict] = []
    for exercise in exercises:
        if any(val in exercise['muscle_group'] for val in muscle_group):
            exercise_filtered.append(exercise)
    return exercise_filtered

def get_exercise_from_body_part(exercises:list[dict],body_part:str)->list[dict]:
    exercise_filtered: list[dict] = []
    for exercise in exercises:
        if exercise['body_part'] == body_part:
            exercise_filtered.append(exercise)
    return exercise_filtered

def get_exercise_from_category(exercises:list[dict],category:str)->list[dict]:
    exercise_filtered: list[dict] = []
    for exercise in exercises:
        if exercise['body_part'] == category:
            exercise_filtered.append(exercise)
    return exercise_filtered

def get_exercise_from_target(exercises:list[dict],target:str)->list[dict]:
    exercise_filtered: list[dict] = []
    for exercise in exercises:
        if exercise['target'] == target:
            exercise_filtered.append(exercise)
    return exercise_filtered