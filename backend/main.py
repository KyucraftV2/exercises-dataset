from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import scripting as s

from . import auth, plans, storage
from .ratelimit import RateLimiter
from .selector import get_mode, get_supported_langs, run_selector

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"

SESSION_COOKIE = "session"

# The chat endpoint costs real money per call (each hits the Claude API, up
# to MAX_TOOL_ITERATIONS times) and is now login-gated, so it's rate limited
# per user; login/register have no user identity yet, so per client IP.
CHAT_RATE_LIMIT = RateLimiter(max_requests=20, window_seconds=600)  # 20 / 10 min per user
LOGIN_RATE_LIMIT = RateLimiter(max_requests=10, window_seconds=300)  # 10 / 5 min per IP
REGISTER_RATE_LIMIT = RateLimiter(max_requests=5, window_seconds=3600)  # 5 / hour per IP


def _client_ip(request: Request) -> str:
    # No reverse-proxy header handling (X-Forwarded-For) - fine for a
    # single-process deployment talked to directly; add trusted-proxy
    # handling if this ever sits behind one.
    return request.client.host if request.client else "unknown"


class IpRateLimitDependency:
    """FastAPI dependency: rejects with 429 once `limiter` denies the
    calling IP. A class (not a closure) so each registered limiter carries
    its own message without needing `functools.partial` gymnastics."""

    def __init__(self, limiter: RateLimiter, message: str) -> None:
        self._limiter = limiter
        self._message = message

    def __call__(self, request: Request) -> None:
        if not self._limiter.allow(_client_ip(request)):
            raise HTTPException(status_code=429, detail=self._message)


require_login_rate_limit = IpRateLimitDependency(
    LOGIN_RATE_LIMIT, "Too many login attempts - please wait a few minutes and try again"
)
require_register_rate_limit = IpRateLimitDependency(
    REGISTER_RATE_LIMIT, "Too many registration attempts - please wait a while and try again"
)
# Custom header a cross-site <form> submission can't attach and a cross-site
# script can't add without triggering a CORS preflight our server won't
# satisfy. Combined with SameSite=Strict on the session cookie, this covers
# both session-riding CSRF and login CSRF (forcing a victim's browser to log
# into an attacker-controlled account).
CSRF_HEADER_VALUE = "XMLHttpRequest"

storage.init_db()

app = FastAPI(title="Exercises AI Selector")


# The whole frontend is now self-hosted with no inline <script>/<style> (see
# web/app.js, web/style.css) and no third-party assets, so the policy can be
# this strict without breaking anything.
_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'"
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = _CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    return response


def get_current_username(session: str | None = Cookie(default=None)) -> str:
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    username = storage.get_username_for_token(session)
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return username


def verify_csrf_header(x_requested_with: str = Header(default="")) -> None:
    if x_requested_with != CSRF_HEADER_VALUE:
        raise HTTPException(status_code=403, detail="Missing or invalid CSRF header")


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=int(storage.SESSION_TTL.total_seconds()),
        path="/",
    )


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


class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    username: str


@app.post("/api/auth/register", response_model=AuthResponse)
def register(
    req: AuthRequest,
    response: Response,
    _rate: None = Depends(require_register_rate_limit),
    _csrf: None = Depends(verify_csrf_header),
) -> AuthResponse:
    if not auth.validate_username(req.username):
        raise HTTPException(
            status_code=400,
            detail="Username must be 3-32 characters: letters, digits, underscore or hyphen",
        )
    if not auth.validate_password(req.password):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Password must be {auth.MIN_PASSWORD_LENGTH} to {auth.MAX_PASSWORD_LENGTH} characters"
            ),
        )
    try:
        token = storage.create_user(req.username, req.password)
    except storage.UsernameTaken:
        raise HTTPException(status_code=409, detail="Username already taken")
    _set_session_cookie(response, token)
    return AuthResponse(username=req.username)


@app.post("/api/auth/login", response_model=AuthResponse)
def login(
    req: AuthRequest,
    response: Response,
    _rate: None = Depends(require_login_rate_limit),
    _csrf: None = Depends(verify_csrf_header),
) -> AuthResponse:
    token = storage.login(req.username, req.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    _set_session_cookie(response, token)
    return AuthResponse(username=req.username)


@app.post("/api/auth/logout")
def logout(
    response: Response,
    session: str | None = Cookie(default=None),
    _csrf: None = Depends(verify_csrf_header),
) -> dict:
    if session:
        storage.logout(session)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(username: str = Depends(get_current_username)) -> dict:
    return {"username": username}


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


class SwapRequest(BaseModel):
    day_index: int
    exercise_id: str


@app.get("/api/plan")
def get_my_plan(lang: str | None = None, username: str = Depends(get_current_username)) -> dict:
    if lang is not None and lang not in s.list_languages():
        raise HTTPException(status_code=400, detail=f"Unsupported lang '{lang}'")
    plan = plans.get_plan(username, lang)
    if plan is None:
        raise HTTPException(status_code=404, detail="No saved plan")
    return plan


@app.put("/api/plan")
def put_my_plan(
    body: PlanIn,
    username: str = Depends(get_current_username),
    _csrf: None = Depends(verify_csrf_header),
) -> dict:
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
def delete_my_plan(
    username: str = Depends(get_current_username), _csrf: None = Depends(verify_csrf_header)
) -> dict:
    storage.delete_plan(username)
    return {"ok": True}


@app.patch("/api/plan/exercise/done")
def mark_exercise_done(
    body: DoneRequest,
    username: str = Depends(get_current_username),
    _csrf: None = Depends(verify_csrf_header),
) -> dict:
    if not plans.set_exercise_done(username, body.day_index, body.exercise_id, body.done):
        raise HTTPException(status_code=404, detail="Plan, day, or exercise not found")
    return plans.get_plan(username)


@app.post("/api/plan/exercise/swap")
def swap_plan_exercise(
    body: SwapRequest,
    username: str = Depends(get_current_username),
    _csrf: None = Depends(verify_csrf_header),
) -> dict:
    updated = plans.swap_exercise(username, body.day_index, body.exercise_id)
    if updated is None:
        raise HTTPException(
            status_code=404, detail="Plan, day, exercise not found, or no alternative available"
        )
    return updated


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    username: str = Depends(get_current_username),
    _csrf: None = Depends(verify_csrf_header),
) -> ChatResponse:
    if not CHAT_RATE_LIMIT.allow(username):
        raise HTTPException(
            status_code=429, detail="Too many chat requests - please slow down and try again shortly"
        )
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
