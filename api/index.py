"""TECHSPARK college fest chatbot backend.

FastAPI service that answers student questions about the TECHSPARK fest
using the Google Gemini API. All fest information comes from a JSON file and
the model instructions come from a separate system prompt file; both are
loaded at runtime and supplied to Gemini on every request.
"""
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from google import genai
from google.genai import types
from google.genai import errors as genai_errors

app = FastAPI(title="TECHSPARK Chatbot API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://10.216.144.59:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FEST_DATA_PATH = PROJECT_ROOT / "config" / "fest_data.json"
SYSTEM_PROMPT_PATH = PROJECT_ROOT / "config" / "system_prompt.txt"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or "gemini-2.0-flash"
GEMINI_TEMPERATURE = float(os.environ.get("GEMINI_TEMPERATURE") or "0.2")
GEMINI_MAX_OUTPUT_TOKENS = int(os.environ.get("GEMINI_MAX_OUTPUT_TOKENS") or "400")

MAX_QUESTION_LENGTH = 1000

REFUSAL_ANSWER = (
    "I'm here to help with TECHSPARK fest information. "
    "Please ask me something about the fest!"
)
SERVICE_UNAVAILABLE_ANSWER = (
    "Sorry, the fest assistant is temporarily unavailable. Please try again shortly."
)
RATE_LIMITED_ANSWER = (
    "Sorry, the fest assistant is receiving too many questions right now. "
    "Please wait a moment and try again."
)
INVALID_KEY_ANSWER = (
    "Sorry, the assistant's AI service is not configured properly right now. "
    "Please try again later."
)
FALLBACK_ANSWER = (
    "Sorry, I could not get a response from the fest assistant right now. "
    "Please try again in a moment!"
)

RATE_LIMIT_MAX_REQUESTS = int(os.environ.get("CHAT_RATE_LIMIT_MAX") or "10")
RATE_LIMIT_WINDOW_SECONDS = float(
    os.environ.get("CHAT_RATE_LIMIT_WINDOW_SECONDS") or "60"
)

FEST_KEYWORDS = (
    "techspark",
    "tech",
    "spark",
    "fest",
    "festival",
    "event",
    "code",
    "hack",
    "robot",
    "quiz",
    "brain",
    "design",
    "sprint",
    "speaker",
    "guest",
    "regist",
    "fee",
    "prize",
    "rule",
    "venue",
    "campus",
    "compet",
    "workshop",
    "contact",
    "organizer",
    "support",
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("techspark-chatbot")


class ConfigError(Exception):
    """Raised when the chat configuration files cannot be loaded or validated."""


class MissingAPIKeyError(Exception):
    """Raised when GEMINI_API_KEY is not configured."""


class InvalidAPIKeyError(Exception):
    """Raised when Gemini rejects the configured API key."""


class RateLimitError(Exception):
    """Raised when Gemini responds with a rate limit error."""


class GeminiTimeoutError(Exception):
    """Raised when the Gemini request times out."""


class GeminiServiceError(Exception):
    """Raised when the Gemini service fails for an unrelated reason."""


class GeminiEmptyResponseError(Exception):
    """Raised when Gemini returns no usable answer text."""


class FestDates(BaseModel):
    start: str
    end: str


class FestEvent(BaseModel):
    name: str
    description: str


class FestSpeaker(BaseModel):
    name: str
    role: str
    organization: str


class FestRegistration(BaseModel):
    deadline: str
    fee: str
    eligibility: str
    url: str
    includes: list


class FestContacts(BaseModel):
    email: str
    phone: str
    instagram: str


class FestInfo(BaseModel):
    fest_name: str
    description: str
    dates: FestDates
    venue: str
    events: list
    speakers: list
    registration: FestRegistration
    rules: list
    contacts: FestContacts


class ChatQuestion(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=MAX_QUESTION_LENGTH,
        description="Student's question about the TECHSPARK fest.",
    )

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Question must not be empty or whitespace-only.")
        return stripped


@lru_cache(maxsize=8)
def _load_fest_data_cached(path: Path) -> FestInfo:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError("Fest information file was not found.") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError("Fest information file is not valid JSON.") from exc

    try:
        return FestInfo.model_validate(raw)
    except Exception as exc:
        raise ConfigError("Fest information file has an invalid structure.") from exc


def _load_fest_data() -> FestInfo:
    return _load_fest_data_cached(FEST_DATA_PATH)


@lru_cache(maxsize=8)
def _load_system_prompt_cached(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, UnicodeDecodeError) as exc:
        raise ConfigError("System prompt file could not be loaded.") from exc

    if not text:
        raise ConfigError("System prompt file is empty.")

    return text


def _load_system_prompt() -> str:
    return _load_system_prompt_cached(SYSTEM_PROMPT_PATH)


def _is_fest_related(question: str) -> bool:
    lowered = question.lower()
    tokens = set(re.findall(r"[a-z0-9]+", lowered))
    if any(keyword in lowered for keyword in FEST_KEYWORDS):
        return True
    return any(keyword in tokens for keyword in FEST_KEYWORDS)


_rate_limit_store: dict = defaultdict(deque)


def _check_rate_limit(key: str) -> bool:
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    timestamps = _rate_limit_store[key]
    while timestamps and timestamps[0] < window_start:
        timestamps.popleft()
    if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
        return False
    timestamps.append(now)
    return True


def _extract_response_text(response) -> str:
    try:
        feedback = response.prompt_feedback
        blocked = getattr(feedback, "block_reason", None) is not None
    except Exception:
        blocked = False

    if blocked:
        raise GeminiEmptyResponseError()

    try:
        text = response.text
    except Exception:
        text = None

    answer_text = (text or "").strip() if isinstance(text, str) else ""
    if not answer_text:
        raise GeminiEmptyResponseError()

    return answer_text


def _generate_answer(question: str, system_prompt: str, fest_info: FestInfo) -> str:
    if not GEMINI_API_KEY:
        raise MissingAPIKeyError()

    client = genai.Client(api_key=GEMINI_API_KEY)
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=(
                f"FEST INFORMATION:\n"
                f"{json.dumps(fest_info.model_dump(mode='json'), indent=2, default=str)}\n\n"
                f"Student's question: {question}"
            ),
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=GEMINI_TEMPERATURE,
                max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
            ),
        )
    except genai_errors.APIError as exc:
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None) or 0
        logger.warning("Gemini request failed with status code: %s", code)
        if code == 429:
            raise RateLimitError() from exc
        if code in (401, 403):
            raise InvalidAPIKeyError() from exc
        raise GeminiServiceError() from exc
    # except Exception as exc:
    #     logger.warning("Gemini request failed: %s", type(exc).__name__)
    #     if isinstance(exc, TimeoutError):
    #         raise GeminiTimeoutError() from exc
    #     raise GeminiServiceError() from exc
    except genai_errors.APIError as exc:
        logger.exception("Gemini API error")
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None) or 0

        if code == 429:
            raise RateLimitError() from exc
        if code in (401, 403):
            raise InvalidAPIKeyError() from exc
        raise GeminiServiceError() from exc

    except Exception as exc:
        logger.exception(
            "Unexpected Gemini request error: %s",
            type(exc).__name__,
        )
        if isinstance(exc, TimeoutError):
            raise GeminiTimeoutError() from exc
        raise GeminiServiceError() from exc

    return _extract_response_text(response)


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse(status_code=200, content={"status": "ok"})


@app.post("/api/chat")
def chat(request: Request, payload: ChatQuestion) -> JSONResponse:
    question = payload.question

    if not _is_fest_related(question):
        return JSONResponse(status_code=200, content={"answer": REFUSAL_ANSWER})

    client_ip = "unknown"
    if request.client is not None and request.client.host:
        client_ip = request.client.host
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()

    if not _check_rate_limit(client_ip):
        return JSONResponse(
            status_code=429, content={"answer": RATE_LIMITED_ANSWER}
        )

    try:
        system_prompt = _load_system_prompt()
        fest_info = _load_fest_data()
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return JSONResponse(
            status_code=503, content={"answer": SERVICE_UNAVAILABLE_ANSWER}
        )

    try:
        answer = _generate_answer(question, system_prompt, fest_info)
    except MissingAPIKeyError:
        logger.warning("GEMINI_API_KEY is not configured; skipping Gemini call.")
        return JSONResponse(
            status_code=503, content={"answer": SERVICE_UNAVAILABLE_ANSWER}
        )
    except InvalidAPIKeyError:
        logger.warning("Gemini rejected the configured API key.")
        return JSONResponse(status_code=503, content={"answer": INVALID_KEY_ANSWER})
    except RateLimitError:
        return JSONResponse(status_code=503, content={"answer": RATE_LIMITED_ANSWER})
    except GeminiTimeoutError:
        return JSONResponse(
            status_code=503, content={"answer": SERVICE_UNAVAILABLE_ANSWER}
        )
    except GeminiServiceError:
        return JSONResponse(
            status_code=503, content={"answer": SERVICE_UNAVAILABLE_ANSWER}
        )
    except GeminiEmptyResponseError:
        return JSONResponse(status_code=200, content={"answer": FALLBACK_ANSWER})
    except Exception:
        logger.exception("Unexpected error while generating the fest answer.")
        return JSONResponse(
            status_code=500, content={"answer": SERVICE_UNAVAILABLE_ANSWER}
        )

    return JSONResponse(status_code=200, content={"answer": answer})
