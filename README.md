# TECHSPARK College Fest Chatbot

An AI-powered chatbot that answers student questions about the **TECHSPARK** college technical fest. Built with FastAPI, Google Gemini, and a vanilla JavaScript chat UI, ready to deploy on Vercel.

## 1. Project Purpose

Students should be able to ask questions about the fest — dates, venue, events, speakers, registration, fees, rules, and contact information — through a simple, modern chat interface.

The application uses **Google Gemini** for generating answers. All fest information is supplied directly in the prompt context on every request (no RAG, vector databases, or retrieval infrastructure). The backend refuses questions that are unrelated to the fest and never invents missing details.

## 2. Architecture and Request Flow

```
Student -> Browser (public/) -> POST /api/chat (api/index.py) -> Gemini (system prompt + fest data + question)
                                                                 |
                                                          GET /api/health
```

1. The frontend (`public/index.html`, `public/style.css`, `public/script.js`) sends the question to the backend via `POST /api/chat` using a **relative** URL (`/api/chat`).
2. The backend (`api/index.py`) validates the question with **Pydantic**.
3. A lightweight, deterministic fest-topic check decides whether the question is fest-related; unrelated questions are politely refused without calling Gemini.
4. The backend loads the system prompt (`config/system_prompt.txt`) and the validated fest data (`config/fest_data.json`).
5. The backend calls **Google Gemini** via the official `google-genai` SDK with:
   - a system instruction (from the system prompt file),
   - the current fest information (from the JSON file),
   - the student's question as the user content.
6. The answer is returned to the frontend as `{"answer": "..."}`.

No API key ever reaches the frontend. The frontend only talks to the FastAPI backend.

## 3. Technology Stack

- **Frontend:** HTML5, CSS3, Vanilla JavaScript (responsive, accessible chat UI).
- **Backend:** Python, FastAPI, Pydantic.
- **AI:** Google Gemini (`google-genai` SDK), Flash model, low temperature, generation limit and timeout set.
- **Deployment:** Vercel (FastAPI via the `@vercel/python` runtime, static frontend via the `public/` directory).

## 4. Folder Structure

```
techspark-chatbot/
├── api/
│   └── index.py            # FastAPI app: GET /api/health, POST /api/chat
├── config/
│   ├── fest_data.json      # Editable fest information (organizers edit this)
│   └── system_prompt.txt   # Chatbot system instructions (organizers edit this)
├── public/
│   ├── index.html          # Chat UI markup
│   ├── style.css           # Chat UI styles
│   └── script.js           # Chat UI logic (calls /api/chat)
├── tests/
│   ├── conftest.py         # Test fixtures (FastAPI TestClient, Gemini mock)
│   └── test_api.py         # API tests (Gemini mocked, no real API key needed)
├── requirements.txt
├── vercel.json
├── .env.example
├── README.md
├── server.js               # Legacy Express prototype (unused)
└── festContent.txt         # Legacy raw fest content (unused)
```

## 5. Prerequisites

- Python 3.11+
- A Google Gemini API key (from [Google AI Studio / aistudio.google.com](https://aistudio.google.com/apikey))
- Node.js/npm only needed if you use the legacy `server.js` prototype; not required for the FastAPI app.

## 6. Getting a Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey) (or Google Cloud Console → Gemini API).
2. Create an API key.
3. Enable the Gemini API for the key's project.
4. Restrict the key to the Gemini API (recommended).

## 7. Environment Variables

Copy `.env.example` to `.env` and fill in real values locally:

```
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash
GEMINI_TIMEOUT_SECONDS=10
GEMINI_TEMPERATURE=0.2
GEMINI_MAX_OUTPUT_TOKENS=400
CHAT_RATE_LIMIT_MAX=10
CHAT_RATE_LIMIT_WINDOW_SECONDS=60
```

- `GEMINI_API_KEY` — required. Server-side only; never exposed to the frontend or committed.
- `GEMINI_MODEL` — Gemini model name; configurable via environment variable (default: `gemini-2.0-flash`).
- `GEMINI_TIMEOUT_SECONDS` — Gemini request timeout (default `10`).
- `GEMINI_TEMPERATURE` — generation temperature for factual answers (default `0.2`).
- `GEMINI_MAX_OUTPUT_TOKENS` — max tokens for the answer (default `400`).
- `CHAT_RATE_LIMIT_MAX` / `CHAT_RATE_LIMIT_WINDOW_SECONDS` — best-effort in-memory rate limit (default 10 requests / 60s). In-memory only; not globally reliable across serverless instances.

### Vercel environment variables

In the Vercel dashboard: **Project Settings → Environment Variables** → add:

- `GEMINI_API_KEY` = your key
- `GEMINI_MODEL` = `gemini-2.0-flash`

Then **redeploy** the project for the new values to take effect.

## 8. Installation

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
pip install pytest httpx       # test dependencies
```

## 9. Running Locally

```bash
uvicorn api.index:app --reload --port 8000
```

The API is then available at `http://127.0.0.1:8000/api/health` and `http://127.0.0.1:8000/api/chat`.

## 10. Testing the API with curl

```bash
curl http://127.0.0.1:8000/api/health
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What events are available?"}'
```

Expected success response:

```json
{ "answer": "The fest features CodeStorm, RoboRush, Brainwave, and DesignSprint." }
```

## 11. Running the Automated Tests

```bash
python -m pytest tests/ -v
```

The tests mock all Gemini API calls, so no real API key or quota is required.

## 12. Deployment to Vercel

The app is configured for a **single Vercel project**:

- Backend: FastAPI app exported as `app` from `api/index.py` (detected automatically by the `@vercel/python` runtime).
- Frontend: static files in `public/` served from the CDN.
- Routing: `/api/*` handled by FastAPI; everything else served as static frontend.

Deploy steps:

1. Push the repository to GitHub.
2. Import the repo into Vercel as a **Python** project.
3. Vercel auto-detects FastAPI from `requirements.txt`.
4. Add the environment variables listed above.
5. Deploy.

Do not run `uvicorn` manually for production; Vercel runs the function.

## 13. Updating Fest Information

Edit `config/fest_data.json` — no code change required. The backend validates the JSON structure and returns a safe service error if it is invalid.

> **Important:** Changes to a committed JSON file generally require a new deployment to become available in production.

## 14. Changing the System Prompt

Edit `config/system_prompt.txt`. The backend loads it on each request (cached per instance).

## 15. Troubleshooting

- **Gemini errors / quota / invalid key:** check Vercel function logs; the API returns friendly messages for missing/invalid/rate-limited/timeout errors.
- **Deployment issues:** ensure `requirements.txt` lists `fastapi`, `uvicorn`, `google-genai`, `pydantic`; ensure `api/index.py` defines `app`.
- **CORS:** not needed because the frontend and API share the same domain via relative URLs.

## 16. Free-Tier Limitations

- Vercel Hobby plan: serverless function limits, cold starts, and Gemini quotas apply.
- In-memory rate limiting is best-effort and not globally reliable across serverless instances.

## 17. Sample Data Warning

The example fest details (dates, venue, events, speakers, fees, contacts) in `config/fest_data.json` are **not verified official information**. Organizers must replace them with confirmed details before publishing. Dates are intentionally kept in the past as sample data.

## 18. Manual Testing Checklist for Live Model Behavior

- Ask: "When is the fest?" → dates/venue answer.
- Ask: "What events are available?" → list of events.
- Ask: "What is the registration fee?" → fee from data.
- Ask: "Who is the chief guest?" → missing info → not invented.
- Ask: "What is the capital of France?" → polite refusal.
- Ask during Gemini outage → friendly unavailable message.

---

## Development Workflow Summary

1. Inspect repo ✅
2. Implement config ✅
3. Implement backend ✅
4. Input validation & error handling ✅
5. Frontend ✅
6. Vercel config ✅
7. Tests ✅
8. Local verification & README ✅ (in progress)
