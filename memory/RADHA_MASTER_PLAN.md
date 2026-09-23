# RADHA — Master Implementation Plan (A.utomateX)

## Principle
Transform incrementally. Never replace working code with placeholders. Every phase ends with REAL, tested functionality. Capabilities needing external providers are built as modular abstractions and marked "requires configuration" rather than faked.

## Current State (done)
- Auth (JWT, bcrypt, per-user isolation), MongoDB (users/conversations/messages).
- AI Runtime + ModelRouter + 3 real providers (Anthropic/OpenAI/Gemini via Universal Key).
- Streaming chat, stop, regenerate (multi-model), persistence, rename/delete/search, export, per-conversation model memory.

## Provider strategy
- **No external key needed (Universal Key)**: text LLMs (Claude/GPT/Gemini), OpenAI image gen (GPT Image 1), Gemini image (Nano Banana), OpenAI Whisper (STT), OpenAI TTS, OpenAI embeddings.
- **Needs a key / config (built as abstraction, marked "requires configuration")**: web search (Tavily/Serper/Perplexity), video generation (fal.ai etc.), Python sandbox infra, GitHub/Slack/Google integrations, payments (Stripe test key available in env).
- **Object storage**: Emergent Object Storage (no keys).
- **Vector/RAG**: OpenAI embeddings (Universal Key) + MongoDB vector similarity.

## Phases
- **P1 Foundation** — DONE (auth, DB, chat, router, streaming, conversations).
- **P2 Projects + Files + Knowledge + Memory** — DONE (2026-06-23). Projects CRUD; real file upload to Emergent Object Storage; text extraction (PDF/DOCX/XLSX/CSV/TXT/MD/JSON); chunking; LOCAL fastembed embeddings (BGE-small, 384-dim, no external key); Python cosine retrieval over per-project chunks; RAG-grounded chat with source citations; project custom instructions; user + project memory with full user control. Frontend: icon-rail nav, Projects list, Project detail (files/instructions/memory/conversations), project-scoped chat, citation chips.
- **P3 Research + Data + Vision** — web search (requires search key), multi-step research + citations; CSV/Excel analysis + charts (sandboxed Python, requires sandbox infra); image understanding (Universal Key).
- **P4 Image + Audio + Video** — image gen (Universal Key), STT/TTS (Universal Key), video engine abstraction (requires video provider key).
- **P5 Coding + Build + Sandbox** — code gen/review/tests; Build mode + sandbox + preview + GitHub (requires sandbox + GitHub config).
- **P6 Tools + Agents + Background jobs** — tool framework, agent runtime, job queue.
- **P7 Automation + Workflow builder**.
- **P8 Billing + Usage + Admin + API platform**.
- **P9 Mobile-ready API hardening + advanced integrations**.

## Cross-cutting (added as phases land)
- Background jobs (needed by P3 research, P4 video, P5 build) — introduce a job queue + status model when first needed.
- Observability: structured logging, request/job IDs.
- Security: authz on every resource, input/output validation, treat files/web/model/tool output as untrusted, sandboxing, audit logs.
- DB grows: Project, Memory, File, FileChunk, KnowledgeItem, Task, Agent/AgentRun, Tool/ToolRun, Workflow/WorkflowRun, Usage, Subscription, GeneratedAsset, ApiKey, AuditLog.

## Acceptance tests to target (real systems, not simulated)
Explain / Research+cite / multi-PDF diff / Excel analysis+charts / presentation gen / image gen / video gen / debug code / build app / autonomous build / scheduled automation / project memory recall.
