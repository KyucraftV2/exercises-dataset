import scripting as s

from . import storage

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _hydrate(days: list[dict], lang: str) -> list[dict]:
    hydrated = []
    for day in days:
        exercises = []
        for item in day.get("exercises", []):
            exercise = s.get_exercise_by_id(item["exercise_id"], lang)
            if exercise is None:
                continue  # dataset changed under us since this was saved - skip rather than crash
            exercises.append(
                {
                    "exercise": exercise,
                    "sets": item.get("sets"),
                    "reps": item.get("reps"),
                    "rest_seconds": item.get("rest_seconds"),
                    "done": bool(item.get("done", False)),
                }
            )
        hydrated.append({"weekday": day.get("weekday"), "label": day.get("label", ""), "exercises": exercises})
    return hydrated


def get_plan(username: str, lang: str | None = None) -> dict | None:
    stored = storage.get_plan(username)
    if stored is None:
        return None
    return {"lang": stored["lang"], "days": _hydrate(stored["days"], lang or stored["lang"])}


def save_plan(username: str, lang: str, days: list[dict]) -> None:
    lean_days = []
    for day in days:
        lean_exercises = [
            {
                "exercise_id": item["exercise_id"],
                "sets": item.get("sets"),
                "reps": item.get("reps"),
                "rest_seconds": item.get("rest_seconds"),
                "done": bool(item.get("done", False)),
            }
            for item in day.get("exercises", [])
        ]
        lean_days.append({"weekday": day.get("weekday"), "label": day.get("label", ""), "exercises": lean_exercises})
    storage.save_plan(username, lang, lean_days)


def set_exercise_done(username: str, day_index: int, exercise_id: str, done: bool) -> bool:
    stored = storage.get_plan(username)
    if stored is None:
        return False
    days = stored["days"]
    if not 0 <= day_index < len(days):
        return False
    for item in days[day_index].get("exercises", []):
        if item.get("exercise_id") == exercise_id:
            item["done"] = done
            storage.save_plan(username, stored["lang"], days)
            return True
    return False
