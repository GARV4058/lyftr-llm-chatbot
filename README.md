# Lyftr AI - LLM Chatbot with Key Failover and Response Caching

A production-grade, resilient full-stack LLM chatbot system featuring automated multi-key failover across API providers, LiteLLM built-in response caching, per-request token telemetry, and multi-turn session persistence using SQLite.

---

## 1. Live URLs

- **Frontend Application**: [https://lyftr-llm-chatbot.vercel.app](https://lyftr-llm-chatbot.vercel.app) *(or live deployment URL)*
- **Backend API Gateway**: [https://lyftr-llm-backend.onrender.com](https://lyftr-llm-backend.onrender.com)
- **Health Check Endpoint**: [https://lyftr-llm-backend.onrender.com/health](https://lyftr-llm-backend.onrender.com/health)

> Both frontend and backend are deployed, public, and connected with full CORS support.

---

## 2. Run locally: with Docker and without

### Option A: Running with Docker (Recommended)

The entire full-stack application (FastAPI backend + React frontend + SQLite persistent volume) can be spun up with a single command via the included `Makefile`:

```bash
# Build and start both services in the background
make up
```

- **Backend**: Accessible at [http://localhost:8000](http://localhost:8000)
- **Frontend**: Accessible at [http://localhost:3000](http://localhost:3000)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

To view real-time logs:
```bash
make logs
```

To stop all containers and clean up:
```bash
make down
```

---

### Option B: Running without Docker

#### Prerequisites
- Python 3.10+
- Node.js 18+ & npm

#### 1. Setup Backend
```bash
cd backend

# Create and activate a Python virtual environment
python -m venv venv
# On Linux/macOS:
source venv/bin/activate
# On Windows:
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
export LLM_API_KEYS="your_key_1,your_key_2"
export DATABASE_URL="sqlite:///./data/app.db"
export ALLOWED_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"
export ENABLE_FAILURE_SIMULATION="true"
export LLM_MODEL="gemini/gemini-2.0-flash"

# Start FastAPI server with Uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 2. Setup Frontend
```bash
cd frontend

# Install frontend dependencies
npm install

# Start Vite development server
npm run dev
```
The frontend UI will be running at [http://localhost:3000](http://localhost:3000).

#### 3. Running Backend Tests
The backend test suite is powered by `pytest` and `httpx`, testing every single contract rule (health check, 422 validations, caching accuracy, multi-key failover, wildcard failures, and session persistence):

```bash
cd backend
pytest tests -v
```

Or via Docker:
```bash
make test
```

---

## 3. Design decisions: key fallback, caching, SQLite session storage

### 1. Key Fallback & Provider Resilience
- **Ordered Key Pool**: Configured via `LLM_API_KEYS` (or `LLM API KEYS`), keys are loaded as an ordered list indexed as `key_1`, `key_2`, ..., `key_n`.
- **Automatic Fallback on Failure**: During live inference, requests sequentially attempt `key_1`. If a key encounters HTTP 429 (rate limit), quota exhaustion, or any 5xx server error, the gateway automatically catches the failure, increments `fallback_attempts`, and fails over to `key_2`.
- **Security & Anonymity**: Raw API secrets are never returned to clients or logged. The client only sees `key_id` (`"key_1"`, `"key_2"`), and on cache hits `key_id` is strictly `null`.
- **Graceful Terminal Failure**: If all keys fail or are exhausted, the gateway responds with HTTP 503 `{"detail": "all providers unavailable"}` and strictly discards the failed request from SQLite history.

### 2. LiteLLM Response Caching
- **Canonical Cache Key**: Cache keys are generated deterministically as `SHA-256(model + canonical_json(system_prompt + history + new_message))`.
- **Zero Hallucination Across Turns**: Because the full message history is baked into the cache key, identical first messages across different sessions hit the cache (`LLM_CACHE`), but subsequent turns with differing history never collide with past turns.
- **Sub-Millisecond Retrieval**: Responses served from cache return with `resolution_source: "LLM_CACHE"`, `key_id: null`, `fallback_attempts: 0`, and original token usage.
- **Failover Simulation Bypass**: When `ENABLE_FAILURE_SIMULATION=true` and an active `X-Simulate-Failure` header is provided, the cache lookup is bypassed so testers can verify key failover behavior deterministically on demand.

### 3. SQLite Session Storage
- **Pure SQLite Architecture**: No Redis or Postgres dependencies. The database file lives inside a mounted Docker volume (`/data/app.db`) set through `DATABASE_URL`, ensuring conversation history persists across container restarts.
- **Automatic Schema Initialization**: The `messages` table is created automatically on application startup:
  ```sql
  CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id, id);
  ```
- **Session Isolation & Multi-turn Context**: Client requests only send the new message and `session_id`. The backend reconstructs prior turns in chronological order.
- **Strict Exclusion of Failed Requests**: Only 200 OK responses are committed to the database; any 422 or 503 request is never saved.
- **Clean Session History API**: `GET /sessions/{session_id}/messages` returns messages oldest first, excludes the system prompt, and returns HTTP 404 `{"detail": "session not found"}` for unknown sessions.

---

## 4. Verification: how to see failover, cache hits and per-message token usage

### 1. Verifying Response Caching (`LLM_CACHE`)
1. Open the UI at [http://localhost:3000](http://localhost:3000).
2. Send: `"What is the speed of light?"`.
   - UI shows: `LIVE_INFERENCE`, `key_1`, latency ~600–1200 ms, Prompt Tokens ~16, Completion Tokens ~18.
3. Click **"+ New Session"** (or refresh page) to initialize a brand new session.
4. Send the identical message: `"What is the speed of light?"`.
   - UI immediately shows: `LLM_CACHE`, `key_id: none (cached)`, `fallback_attempts: 0`, latency ~1–5 ms, and identical token usage!

#### Via cURL:
```bash
# First request (LIVE_INFERENCE)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "session-1", "message": "What is the speed of light?"}'

# Second request in fresh session (LLM_CACHE)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "session-2", "message": "What is the speed of light?"}'
```

---

### 2. Verifying Key Failover (`X-Simulate-Failure`)
You can trigger failover directly in the frontend UI using the **"Failure Simulation"** dropdown, or via cURL:

#### A. Simulating Key 1 Failure (Failover to Key 2)
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: key_1=429" \
  -d '{"session_id": "sim-test-1", "message": "Explain key failover."}'
```
**Response (200 OK):**
```json
{
  "session_id": "sim-test-1",
  "reply": "...",
  "metadata": {
    "resolution_source": "LIVE_INFERENCE",
    "model": "gemini/gemini-2.0-flash",
    "key_id": "key_2",
    "fallback_attempts": 1,
    "input_tokens": 14,
    "output_tokens": 30
  }
}
```

#### B. Simulating Total Provider Failure (All Keys Fail -> 503)
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: *=429" \
  -d '{"session_id": "sim-test-2", "message": "Will fail."}'
```
**Response (503 Service Unavailable):**
```json
{
  "detail": "all providers unavailable"
}
```
Querying session history confirms nothing was saved:
```bash
curl http://localhost:8000/sessions/sim-test-2/messages
# {"detail": "session not found"} (HTTP 404)
```

---

### 3. Verifying Per-Message Token Tracking
- Send a short message (e.g. `"Hi"`) in `session-a`: `input_tokens` ~11, `output_tokens` ~8.
- Send another short message (e.g. `"Hello"`) in `session-b`: `input_tokens` ~11.
- Both report per-request tokens, **never a cumulative conversation total**.

---

## 5. Setup Used: your editor and AI tools

- **Editor & IDE**: VS Code on Windows 11 with PowerShell 7 and WSL2 Docker Engine.
- **AI Tooling & Coding Assistants**:
  - Google Antigravity Agent & Gemini 2.0 / Flash developer ecosystem.
  - Used for rapid scaffolding of Docker multi-stage configurations, SQLite schema design, and comprehensive test harness setup.
- **Runtimes & Frameworks**:
  - Python 3.11 with FastAPI, LiteLLM, Pydantic v2, and Pytest.
  - Node.js 20 with React 18, Vite, and Nginx Alpine.

---

## 6. Bonus features (if any): what you added beyond the requirements and why

1. **Interactive UI Failure Simulation Controller**:
   - Added an on-page simulation dropdown directly inside the chat interface. Reviewers and interviewers can test `key_1=429`, `key_1=500`, and `*=429` scenarios with a single click without opening a terminal or Postman.
2. **Real-Time Gateway Health & Key Pool Telemetry**:
   - Added a dynamic header health badge that queries `GET /health` to display live server connectivity and the active key count in real-time.
3. **Session Management & Instant Session Reset**:
   - Included a `+ New Session` button and a one-click **Copy Session ID** button to easily demonstrate cache isolation between distinct sessions.
4. **Visual Cache & Failover Badges**:
   - Distinct color-coded badges for `⚡ LLM_CACHE` (green) and `🌐 LIVE_INFERENCE` (blue), with dedicated visual tags for `key_id` and `fallback_attempts` (amber badge).
5. **Polished Glassmorphic Design**:
   - Modern dark theme typography with smooth auto-scroll, bouncing typing indicators, and readable error cards for 422 and 503 responses that prevent app crashes.
