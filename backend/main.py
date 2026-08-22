from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import scripting as s

from . import auth, plans, storage
from .selector import get_mode, get_supported_langs, run_selector

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"

storage.init_db()

app = FastAPI(title="Exercises AI Selector")


def get_current_username(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    username = storage.get_username_for_token(authorization.removeprefix("Bearer ").strip())
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return username


class ChatTurn(BaseModel):
    role: str
    text: str


class ChatRequest(BaseModel):
    message: str
    lang: str = "fr"
    history: list[ChatTurn] = []


class ChatResponse(BaseModel):
    message: str
    exercises: list[dict]
    program: dict | None = None


@app.get("/api/languages")
def languages() -> list[str]:
    return s.list_languages()


@app.get("/api/exercise/{exercise_id}")
def get_exercise(exercise_id: str, lang: str = "fr") -> dict:
    if lang not in s.list_languages():
        raise HTTPException(status_code=400, detail=f"Unsupported lang '{lang}'")
    exercise = s.get_exercise_by_id(exercise_id, lang)
    if exercise is None:
        raise HTTPException(status_code=404, detail=f"No exercise with id '{exercise_id}'")
    return exercise


@app.get("/api/mode")
def mode() -> dict:
    return {"mode": get_mode(), "supported_langs": get_supported_langs()}


class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    username: str


@app.post("/api/auth/register", response_model=AuthResponse)
def register(req: AuthRequest) -> AuthResponse:
    if not auth.validate_username(req.username):
        raise HTTPException(
            status_code=400,
            detail="Username must be 3-32 characters: letters, digits, underscore or hyphen",
        )
    if not auth.validate_password(req.password):
        raise HTTPException(
            status_code=400, detail=f"Password must be at least {auth.MIN_PASSWORD_LENGTH} characters"
        )
    try:
        token = storage.create_user(req.username, req.password)
    except storage.UsernameTaken:
        raise HTTPException(status_code=409, detail="Username already taken")
    return AuthResponse(token=token, username=req.username)


@app.post("/api/auth/login", response_model=AuthResponse)
def login(req: AuthRequest) -> AuthResponse:
    token = storage.login(req.username, req.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return AuthResponse(token=token, username=req.username)


@app.post("/api/auth/logout")
def logout(authorization: str = Header(default="")) -> dict:
    if authorization.startswith("Bearer "):
        storage.logout(authorization.removeprefix("Bearer ").strip())
    return {"ok": True}


class PlanExerciseIn(BaseModel):
    exercise_id: str
    sets: int
    reps: str
    rest_seconds: int
    done: bool = False


class PlanDayIn(BaseModel):
    weekday: str | None = None
    label: str = ""
    exercises: list[PlanExerciseIn] = []


class PlanIn(BaseModel):
    lang: str
    days: list[PlanDayIn]


class DoneRequest(BaseModel):
    day_index: int
    exercise_id: str
    done: bool


@app.get("/api/plan")
def get_my_plan(lang: str | None = None, username: str = Depends(get_current_username)) -> dict:
    if lang is not None and lang not in s.list_languages():
        raise HTTPException(status_code=400, detail=f"Unsupported lang '{lang}'")
    plan = plans.get_plan(username, lang)
    if plan is None:
        raise HTTPException(status_code=404, detail="No saved plan")
    return plan


@app.put("/api/plan")
def put_my_plan(body: PlanIn, username: str = Depends(get_current_username)) -> dict:
    if body.lang not in s.list_languages():
        raise HTTPException(status_code=400, detail=f"Unsupported lang '{body.lang}'")
    for day in body.days:
        if day.weekday is not None and day.weekday not in plans.WEEKDAYS:
            raise HTTPException(status_code=400, detail=f"Invalid weekday '{day.weekday}'")
        exercise_ids = [item.exercise_id for item in day.exercises]
        if len(exercise_ids) != len(set(exercise_ids)):
            raise HTTPException(status_code=400, detail=f"Duplicate exercise in day '{day.label}'")
    plans.save_plan(username, body.lang, [d.model_dump() for d in body.days])
    return plans.get_plan(username, body.lang)


@app.delete("/api/plan")
def delete_my_plan(username: str = Depends(get_current_username)) -> dict:
    storage.delete_plan(username)
    return {"ok": True}


@app.patch("/api/plan/exercise/done")
def mark_exercise_done(body: DoneRequest, username: str = Depends(get_current_username)) -> dict:
    if not plans.set_exercise_done(username, body.day_index, body.exercise_id, body.done):
        raise HTTPException(status_code=404, detail="Plan, day, or exercise not found")
    return plans.get_plan(username)


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if req.lang not in s.list_languages():
        raise HTTPException(status_code=400, detail=f"Unsupported lang '{req.lang}'")
    supported = get_supported_langs()
    if req.lang not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"lang '{req.lang}' isn't supported by AI_MODE='{get_mode()}' (supported: {supported})",
        )
    result = run_selector(req.message, [t.model_dump() for t in req.history], req.lang)
    return ChatResponse(**result)


app.mount("/images", StaticFiles(directory=REPO_ROOT / "images"), name="images")
app.mount("/videos", StaticFiles(directory=REPO_ROOT / "videos"), name="videos")
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
