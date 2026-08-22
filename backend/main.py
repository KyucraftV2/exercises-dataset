from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import scripting as s

from .selector import get_mode, get_supported_langs, run_selector

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"

app = FastAPI(title="Exercises AI Selector")


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


@app.get("/api/exercise/{exercise_id}/alternative")
def get_alternative(exercise_id: str, lang: str = "fr", exclude: str = "") -> dict:
    if lang not in s.list_languages():
        raise HTTPException(status_code=400, detail=f"Unsupported lang '{lang}'")
    exercises_by_lang = s.get_lang(s.load_exercises(), lang)
    exercise = next((ex for ex in exercises_by_lang if ex["id"] == exercise_id), None)
    if exercise is None:
        raise HTTPException(status_code=404, detail=f"No exercise with id '{exercise_id}'")
    exclude_ids = {x for x in exclude.split(",") if x}
    alternative = s.find_alternative(exercises_by_lang, exercise, exclude_ids)
    if alternative is None:
        raise HTTPException(status_code=404, detail="No alternative exercise found")
    return alternative


@app.get("/api/mode")
def mode() -> dict:
    return {"mode": get_mode(), "supported_langs": get_supported_langs()}


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
