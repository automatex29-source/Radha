# RADHA — Product Requirements (A.utomateX)

## Original Problem Statement
Build RADHA, the first AI product of A.utomateX: a real, working AI workspace (not a mockup) with real backend, database, authentication, real LLM integration, and persistent conversations. V1 journey: Login → Workspace → Start Conversation → Send Message → Real AI Model → Streaming Response → Save → Reload → Conversation still exists. Build only V1, but build it properly, with an architecture that allows memory/files/tools/agents/automation later.

## Architecture
- **Stack**: FastAPI + MongoDB + React (platform equivalent of the requested Next.js/Postgres/Prisma; kept portable/deployable).
- **AI Runtime abstraction**: `RADHA → ModelRouter → ModelProvider → LLM`.
  - `ai_runtime/types.py` (AIRequest, AIResponse, ChatMessage), `base.py` (ModelProvider ABC), `router.py` (ModelRouter registry), `anthropic_provider.py` (single V1 provider via emergentintegrations). Adding OpenAI/Gemini/future A.utomateX models = register a new provider, no chat rewrite.
- **Auth**: JWT bearer tokens (bcrypt hashing), token in localStorage `radha_token`. `auth.py`.
- **DB collections**: users, conversations, messages. Per-user ownership enforced on every conversation/message query.
- **Streaming**: SSE from `POST /api/conversations/{id}/stream`, consumed by frontend `fetch` + ReadableStream.
- **Env**: `AI_API_KEY`, `AI_MODEL`, `AI_PROVIDER`, `AUTH_SECRET`, `MONGO_URL`, `DB_NAME`. Documented in `.env.example`. Keys server-side only.

## User Personas
- Individual professional / builder using a premium AI workspace for reasoning, coding, and synthesis tasks.

## Core Requirements (static)
- Real authentication; unauthenticated users cannot access others' data.
- Real LLM responses (no simulation), streamed.
- Conversations persist and reload.
- Provider-agnostic AI architecture.

## Implemented (2026-06-22)
- JWT auth: register, login, logout, /me, protected routes.
- Conversations CRUD + messages, per-user isolation (verified 404/401).
- Real Claude Sonnet 4.6 streaming via ModelRouter/AnthropicProvider (Emergent Universal Key).
- Premium dark "Obsidian Studio" UI: auth showcase page, sidebar (grouped by date, search, rename, delete), workspace with empty-state starter cards, streaming message thread with markdown + code copy, model selector, composer with auto-grow + stop generation.
- Auto-titling of conversations from first message.
- Tested: 11/11 backend pytest + full UI e2e, all green.

## Implemented (2026-06-23)
- Multi-provider AI runtime: added OpenAIProvider + GeminiProvider alongside AnthropicProvider, all registered on ModelRouter. Shared `_emergent.py` streaming helper keeps each provider ~10 lines.
- 4 selectable models (RADHA Omni/Swift = Claude, Vision = GPT-5.4, Flash = Gemini) exposed via /api/models and the top-bar model selector. Each verified streaming real tokens with no chat-code changes — proves the provider extensibility from the vision.
- Per-conversation model memory: conversation stores last-used model, restored on reopen (verified gemini persists).
- Conversation export to markdown (client-side download) via header Export button.
- Regenerate reply: POST /conversations/{id}/regenerate drops the trailing assistant turn and re-streams (optionally on a different model). Verified — old answer replaced, re-answered on Gemini. Shared `_stream_response` helper used by both stream + regenerate.
- Chat attachments: upload a document directly in the composer (POST /conversations/{id}/files) — extracted/chunked/embedded and RAG-grounded into that chat with citations, no project required. Verified "Golden Otter" grounded answer with [note.txt] citation.
- UI polish pass: gradient headline treatment, ambient orbs on empty state, lift-on-hover starter/project cards, refined composer with attach chips.

## Backlog (not built — future foundations already accommodated by architecture)
- **P1**: Memory/context recall across conversations; file/knowledge upload & retrieval.
- **P1**: Additional providers (OpenAI, Gemini) via ModelRouter registration.
- **P2**: Tools/function-calling, agents, workflow automation.
- **P2**: Login brute-force lockout, refresh tokens, migrate to FastAPI lifespan handler, explicit CORS origins.
- **P2**: Conversation export/share, streaming cancellation propagated to provider.

## Next Tasks
- Add file upload + document Q&A (object storage) as the first "knowledge" capability.
- Register a second provider to prove multi-model routing.

## Phase 4 — Agent, vision and voice
- **Agent tool-use framework** (`backend/agent/`): `ToolRegistry` + `run_agent` loop (max 8 steps, last step forces an answer). Tools: `web_search` (Tavily or DuckDuckGo), `fetch_url` (SSRF-guarded), `run_python` (sandbox: rlimits, timeout, no network via `unshare -rn` when available, drops to `nobody`), `generate_image`. Streams SSE `tool` / `tool_result` events; steps + produced media saved on the assistant message.
- **LLM path**: agent turns and any conversation with images go through LiteLLM (`agent/llm.py`) with provider keys or `LLM_GATEWAY_URL`; plain chat still uses the Emergent router.
- **Vision**: `POST /api/media` (images), message `images: [mediaId]`, sent as image parts.
- **Voice**: `POST /api/audio/transcribe`, `POST /api/audio/speech` (OpenAI). UI: mic dictation, "Listen" on replies, hands-free Voice mode (silence detection).
- **Media store**: `media` collection (≤12MB/item), served by `GET /api/media/{id}?auth=`.
- **Capabilities**: `GET /api/capabilities` tells the UI which features are configured.
- **Next phases**: video generation/understanding, browser automation, automations/workflows, app builder + virtual FS, test runner, live preview, deployment, git.
