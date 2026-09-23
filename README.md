# RADHA — the AI workspace by A.utomateX

Chat with Claude, GPT and Gemini, plus agent tools (web search, browser, code
execution), images and video, voice, Excel/PowerPoint/Word/PDF creation with
previews, an app builder with live preview, publishing and git history, and
scheduled automations.

## Run it on your computer (easiest: Docker)

You need **Docker Desktop** and **at least one AI API key**.

1. **Install Docker Desktop** from https://www.docker.com/products/docker-desktop/ and open it.
   (On Windows, accept the prompt to enable WSL 2 if it asks, then restart.)
2. **Download RADHA**: on GitHub click **Code → Download ZIP**, then unzip it.
   (Or: `git clone https://github.com/automatex29-source/Radha`.)
3. **Add your keys**: in the RADHA folder, copy `.env.example` to a new file named `.env`,
   open it in Notepad and paste your key(s) after the `=` signs. Save.
   - Claude: https://console.anthropic.com → API keys → `ANTHROPIC_API_KEY`
   - OpenAI (also needed for images, voice and Sora video): https://platform.openai.com/api-keys → `OPENAI_API_KEY`
   - Gemini (also Veo video): https://aistudio.google.com/apikey → `GEMINI_API_KEY`
4. **Start it**: open a terminal *in the RADHA folder* (Windows: open the folder, click the
   address bar, type `cmd`, press Enter) and run:
   ```
   docker compose up --build
   ```
   The first start downloads and builds everything (about 5–15 minutes). It's ready when you see
   `Application startup complete`.
5. **Open http://localhost:8080**, click **Register**, and create your account.

To stop RADHA press `Ctrl+C` in that terminal. To start it again later, run
`docker compose up` in the same folder. Your chats, apps and files are kept.
After changing `.env`, restart it for the change to take effect.

**Updating** to a newer version: download the new code into the same folder
(keep your `.env`), then run `docker compose up --build`.

### What each key unlocks

| Key | Unlocks |
|---|---|
| `ANTHROPIC_API_KEY` | Claude models: chat, agent mode, app builder, automations |
| `OPENAI_API_KEY` | GPT models, image generation, voice, Sora video |
| `GEMINI_API_KEY` | Gemini models, Veo video |
| `TAVILY_API_KEY` (optional) | Better web search (DuckDuckGo is used otherwise) |

All other settings (video quality, sandbox limits, …) are documented in `backend/.env.example`.

## Development setup (without Docker)

Requirements: Python 3.11+, Node.js 20+, MongoDB running locally.

```bash
# Backend
cd backend
pip install -r requirements.txt
playwright install chromium
cp .env.example .env          # set MONGO_URL, DB_NAME and your API keys
uvicorn server:app --reload --port 8001

# Frontend (second terminal)
cd frontend
npm install
npm run dev                   # http://localhost:3000, proxies /api to :8001
```

Or build the frontend once (`npm run build`) and open http://localhost:8001 — the
backend serves the built app itself.

Backend tests that run offline: `cd backend && pytest tests/test_agent_tools.py tests/test_documents_video_browser.py tests/test_apps_automations.py`.

## Notes

- The code sandbox (Python/terminal tools) uses process limits, and blocks network
  access when the host allows Linux user namespaces (not inside Docker's default settings).
  It is not a virtual machine; don't expose RADHA publicly to untrusted users without
  extra isolation.
- Published apps are served from `/api/sites/<name>/` in a sandboxed origin.
