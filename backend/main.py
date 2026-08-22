from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .assistant import run_assistant

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


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    result = run_assistant(req.message, [t.model_dump() for t in req.history], req.lang)
    return ChatResponse(**result)


app.mount("/images", StaticFiles(directory=REPO_ROOT / "images"), name="images")
app.mount("/videos", StaticFiles(directory=REPO_ROOT / "videos"), name="videos")
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
