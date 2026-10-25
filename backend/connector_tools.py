"""Agent tools for the apps a user connects in Settings > Connectors (see connectors.py).

Each tool is offered only once its app is connected (Tool.connector). Krish reads Drive, Calendar, Gmail, GitHub
and Notion, adds Calendar events, Notion pages and GitHub issues, saves Gmail replies as drafts (never sends
them), and sends messages to the user's own Telegram, WhatsApp, Slack or Discord.
"""
import base64
import re
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Optional

import httpx

import connectors
import extract
from agent.tools import Tool, ToolContext, ToolOutput, ToolRegistry

GAPI = "https://www.googleapis.com"
MAX_READ = 14_000


async def _token(ctx: ToolContext, cid: str) -> str:
    return (await connectors.secret_for(ctx.user_id, cid))["access"]


async def _get(url: str, token: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> httpx.Response:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url, params=params, headers={"Authorization": f"Bearer {token}", **(headers or {})})
    _check(r)
    return r


async def _post(url: str, token: str, body: dict, headers: Optional[dict] = None) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=body, headers={"Authorization": f"Bearer {token}", **(headers or {})})
    _check(r)
    return r.json()


def _check(r: httpx.Response):
    if r.status_code in (401, 403):
        raise RuntimeError("The app refused access. Ask the user to connect it again in Settings > Connectors "
                           f"(it answered {r.status_code}).")
    if r.status_code == 404:
        raise RuntimeError("Not found. Check the name or id, or search first.")
    if r.status_code >= 400:
        try:
            detail = r.json()
            detail = (detail.get("error") or {}).get("message") if isinstance(detail.get("error"), dict) \
                else detail.get("message") or detail.get("error")
        except ValueError:
            detail = r.text[:200]
        raise RuntimeError(f"The app answered {r.status_code}: {detail}")


def _clip(text: str) -> str:
    return text if len(text) <= MAX_READ else text[:MAX_READ] + "\n… [cut; ask for a part if you need more]"


def _q(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'")


# -------------------------------------------------------------------- Drive
_EXPORT = {"application/vnd.google-apps.document": ("text/plain", "txt"),
           "application/vnd.google-apps.spreadsheet": ("text/csv", "csv"),
           "application/vnd.google-apps.presentation": ("text/plain", "txt")}
_EXT = {"application/pdf": "pdf", "text/plain": "txt", "text/csv": "csv", "text/markdown": "md",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "application/json": "json", "text/html": "html"}


async def _drive_search(ctx: ToolContext, args: dict) -> ToolOutput:
    token = await _token(ctx, "google_drive")
    query = (args.get("query") or "").strip()
    q = "trashed = false"
    if query:
        q += f" and (name contains '{_q(query)}' or fullText contains '{_q(query)}')"
    params = {"q": q, "pageSize": max(1, min(int(args.get("max_results") or 10), 25)),
              "fields": "files(id,name,mimeType,modifiedTime,webViewLink,size)"}
    if not query:
        params["orderBy"] = "modifiedTime desc"
    r = await _get(f"{GAPI}/drive/v3/files", token, params)
    files = r.json().get("files", [])
    if not files:
        return ToolOutput(content="No files found in Google Drive." + (" Try other words." if query else ""),
                          summary="No files found")
    lines = [f"- {f['name']} (id: {f['id']}, {f['mimeType'].split('.')[-1].split('/')[-1]}, "
             f"changed {f.get('modifiedTime', '')[:10]}) {f.get('webViewLink', '')}" for f in files]
    return ToolOutput(content="Google Drive files:\n" + "\n".join(lines), summary=f"Found {len(files)} files")


async def _drive_read(ctx: ToolContext, args: dict) -> ToolOutput:
    token = await _token(ctx, "google_drive")
    fid = (args.get("file_id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", fid):
        raise ValueError("Give a file_id from drive_search")
    meta = (await _get(f"{GAPI}/drive/v3/files/{fid}", token, {"fields": "id,name,mimeType,size"})).json()
    mime = meta.get("mimeType", "")
    if mime in _EXPORT:
        r = await _get(f"{GAPI}/drive/v3/files/{fid}/export", token, {"mimeType": _EXPORT[mime][0]})
        text = r.text
    else:
        if int(meta.get("size") or 0) > 15 * 1024 * 1024:
            raise ValueError("That file is too big to read (over 15MB)")
        ext = _EXT.get(mime) or (meta["name"].rsplit(".", 1)[-1].lower() if "." in meta["name"] else "txt")
        r = await _get(f"{GAPI}/drive/v3/files/{fid}", token, {"alt": "media"})
        text = extract.extract_text(r.content, ext, mime)
    if not (text or "").strip():
        return ToolOutput(content=f"{meta['name']} has no text Krish can read.", summary="No text")
    return ToolOutput(content=f"# {meta['name']}\n\n{_clip(text)}", summary=f"Read {meta['name']}")


# ----------------------------------------------------------------- Calendar
def _when(ev: dict) -> str:
    start = ev.get("start") or {}
    if start.get("date"):
        return f"{start['date']} (all day)"
    return (start.get("dateTime") or "")[:16].replace("T", " ")


async def _calendar_events(ctx: ToolContext, args: dict) -> ToolOutput:
    token = await _token(ctx, "google_calendar")
    days = max(1, min(int(args.get("days") or 7), 60))
    start = datetime.now(timezone.utc)
    if args.get("from_date"):
        start = datetime.fromisoformat(str(args["from_date"])[:10]).replace(tzinfo=timezone.utc)
    params = {"timeMin": start.isoformat(), "timeMax": (start + timedelta(days=days)).isoformat(),
              "singleEvents": "true", "orderBy": "startTime", "maxResults": 50}
    if args.get("query"):
        params["q"] = args["query"]
    r = await _get(f"{GAPI}/calendar/v3/calendars/primary/events", token, params)
    body = r.json()
    events = body.get("items", [])
    if not events:
        return ToolOutput(content=f"No events in the next {days} days.", summary="Calendar is free")
    lines = [f"- {_when(e)}: {e.get('summary') or '(no title)'}" + (f" @ {e['location']}" if e.get("location") else "")
             for e in events]
    return ToolOutput(content=f"Calendar ({body.get('timeZone', 'UTC')} time):\n" + "\n".join(lines),
                      summary=f"{len(events)} events")


async def _calendar_add(ctx: ToolContext, args: dict) -> ToolOutput:
    token = await _token(ctx, "google_calendar")
    title = (args.get("title") or "").strip()
    start = (args.get("start") or "").strip()
    if not title or not start:
        raise ValueError("'title' and 'start' are required")
    tz = args.get("timezone") or "Asia/Kolkata"
    if len(start) == 10:  # a date: an all-day event
        end = args.get("end") or (datetime.fromisoformat(start) + timedelta(days=1)).date().isoformat()
        when = {"start": {"date": start}, "end": {"date": end[:10]}}
    else:
        end = args.get("end") or (datetime.fromisoformat(start) + timedelta(minutes=int(args.get("minutes") or 60))).isoformat()
        when = {"start": {"dateTime": start, "timeZone": tz}, "end": {"dateTime": end, "timeZone": tz}}
    event = {"summary": title, **when}
    if args.get("description"):
        event["description"] = args["description"]
    if args.get("location"):
        event["location"] = args["location"]
    if args.get("reminder_minutes") is not None:
        event["reminders"] = {"useDefault": False, "overrides": [{"method": "popup", "minutes": int(args["reminder_minutes"])}]}
    made = await _post(f"{GAPI}/calendar/v3/calendars/primary/events", token, event)
    return ToolOutput(content=f"Added to Google Calendar: {title}, {_when(made)}. Link: {made.get('htmlLink', '')}",
                      summary=f"Added {title}")


# -------------------------------------------------------------------- Gmail
def _header(msg: dict, name: str) -> str:
    return next((h["value"] for h in (msg.get("payload") or {}).get("headers", []) if h["name"].lower() == name.lower()), "")


def _body_text(part: dict) -> str:
    if part.get("mimeType") == "text/plain" and (part.get("body") or {}).get("data"):
        return base64.urlsafe_b64decode(part["body"]["data"] + "==").decode("utf-8", "replace")
    for sub in part.get("parts") or []:
        text = _body_text(sub)
        if text:
            return text
    if part.get("mimeType") == "text/html" and (part.get("body") or {}).get("data"):
        html = base64.urlsafe_b64decode(part["body"]["data"] + "==").decode("utf-8", "replace")
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    return ""


async def _gmail_search(ctx: ToolContext, args: dict) -> ToolOutput:
    token = await _token(ctx, "gmail")
    params = {"maxResults": max(1, min(int(args.get("max_results") or 10), 20))}
    if args.get("query"):
        params["q"] = args["query"]
    ids = (await _get(f"{GAPI}/gmail/v1/users/me/messages", token, params)).json().get("messages", [])
    if not ids:
        return ToolOutput(content="No emails match.", summary="No emails")
    lines = []
    for m in ids:
        msg = (await _get(f"{GAPI}/gmail/v1/users/me/messages/{m['id']}", token,
                          {"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]})).json()
        lines.append(f"- id {m['id']} | {_header(msg, 'Date')[:22]} | From: {_header(msg, 'From')} | "
                     f"{_header(msg, 'Subject')} | {msg.get('snippet', '')[:160]}")
    return ToolOutput(content="Emails:\n" + "\n".join(lines), summary=f"Found {len(ids)} emails")


async def _gmail_read(ctx: ToolContext, args: dict) -> ToolOutput:
    token = await _token(ctx, "gmail")
    mid = (args.get("message_id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9]{6,40}", mid):
        raise ValueError("Give a message_id from gmail_search")
    msg = (await _get(f"{GAPI}/gmail/v1/users/me/messages/{mid}", token, {"format": "full"})).json()
    text = _body_text(msg.get("payload") or {}) or msg.get("snippet", "")
    head = f"From: {_header(msg, 'From')}\nTo: {_header(msg, 'To')}\nDate: {_header(msg, 'Date')}\n" \
           f"Subject: {_header(msg, 'Subject')}\nThread: {msg.get('threadId')}"
    return ToolOutput(content=f"{head}\n\n{_clip(text.strip())}", summary=f"Read: {_header(msg, 'Subject')[:60]}")


async def _gmail_draft(ctx: ToolContext, args: dict) -> ToolOutput:
    token = await _token(ctx, "gmail")
    to, subject, body = (args.get("to") or "").strip(), (args.get("subject") or "").strip(), args.get("body") or ""
    if not to or not body.strip():
        raise ValueError("'to' and 'body' are required")
    mail = EmailMessage()
    mail["To"], mail["Subject"] = to, subject
    mail.set_content(body)
    draft = {"message": {"raw": base64.urlsafe_b64encode(mail.as_bytes()).decode()}}
    if args.get("thread_id"):
        draft["message"]["threadId"] = args["thread_id"]
    await _post(f"{GAPI}/gmail/v1/users/me/drafts", token, draft)
    return ToolOutput(content=f"Saved a draft to {to} in the user's Gmail Drafts. It is NOT sent: tell the user to "
                              "open Gmail > Drafts to check and send it.", summary=f"Draft to {to} saved")


# ------------------------------------------------------------------- GitHub
GH = {"Accept": "application/vnd.github+json"}


async def _github_repos(ctx: ToolContext, args: dict) -> ToolOutput:
    token = await _token(ctx, "github")
    repos = (await _get("https://api.github.com/user/repos", token, {"sort": "updated", "per_page": 30}, GH)).json()
    lines = [f"- {r['full_name']}{' (private)' if r.get('private') else ''}: {r.get('description') or ''}" for r in repos]
    return ToolOutput(content="GitHub repositories:\n" + ("\n".join(lines) or "none"), summary=f"{len(repos)} repositories")


async def _github_read(ctx: ToolContext, args: dict) -> ToolOutput:
    token = await _token(ctx, "github")
    repo = (args.get("repo") or "").strip()
    path = (args.get("path") or "").strip().strip("/")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise ValueError("'repo' must look like owner/name")
    body = (await _get(f"https://api.github.com/repos/{repo}/contents/{path}", token, None, GH)).json()
    if isinstance(body, list):
        lines = [f"- {i['path']}{'/' if i['type'] == 'dir' else ''}" for i in body]
        return ToolOutput(content=f"{repo}/{path}:\n" + "\n".join(lines), summary=f"Listed {repo}/{path}")
    text = base64.b64decode(body.get("content") or "").decode("utf-8", "replace")
    return ToolOutput(content=f"{repo}/{path}:\n```\n{_clip(text)}\n```", summary=f"Read {path}")


async def _github_issue(ctx: ToolContext, args: dict) -> ToolOutput:
    token = await _token(ctx, "github")
    repo = (args.get("repo") or "").strip()
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or not (args.get("title") or "").strip():
        raise ValueError("'repo' (owner/name) and 'title' are required")
    made = await _post(f"https://api.github.com/repos/{repo}/issues", token,
                       {"title": args["title"].strip(), "body": args.get("body") or ""}, GH)
    return ToolOutput(content=f"Opened issue #{made.get('number')}: {made.get('html_url')}", summary=f"Issue #{made.get('number')}")


# ------------------------------------------------------------------- Notion
NH = {"Notion-Version": connectors.NOTION_VERSION}


def _notion_title(page: dict) -> str:
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title", [])) or "Untitled"
    return "".join(t.get("plain_text", "") for t in page.get("title", [])) or "Untitled"


async def _notion_search(ctx: ToolContext, args: dict) -> ToolOutput:
    token = await _token(ctx, "notion")
    body = await _post("https://api.notion.com/v1/search", token,
                       {"query": args.get("query") or "", "page_size": 15}, NH)
    items = body.get("results", [])
    if not items:
        return ToolOutput(content="Nothing found. The user may need to share pages with Krish in Notion "
                                  "(page ••• > Connections).", summary="Nothing found")
    lines = [f"- {_notion_title(i)} ({i['object']}, id: {i['id']}) {i.get('url', '')}" for i in items]
    return ToolOutput(content="Notion:\n" + "\n".join(lines), summary=f"Found {len(items)} pages")


def _block_text(block: dict) -> str:
    kind = block.get("type", "")
    data = block.get(kind) or {}
    text = "".join(t.get("plain_text", "") for t in data.get("rich_text", []))
    prefix = {"heading_1": "# ", "heading_2": "## ", "heading_3": "### ", "bulleted_list_item": "- ",
              "numbered_list_item": "1. ", "to_do": "[x] " if data.get("checked") else "[ ] ", "quote": "> "}.get(kind, "")
    if kind == "child_page":
        return f"(sub-page: {data.get('title', '')}, id {block['id']})"
    return prefix + text if text else ""


async def _notion_read(ctx: ToolContext, args: dict) -> ToolOutput:
    token = await _token(ctx, "notion")
    pid = (args.get("page_id") or "").strip().replace("-", "")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", pid):
        raise ValueError("Give a page_id from notion_search")
    lines, cursor = [], None
    for _ in range(5):
        params = {"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
        body = (await _get(f"https://api.notion.com/v1/blocks/{pid}/children", token, params, NH)).json()
        lines += [t for t in (_block_text(b) for b in body.get("results", [])) if t]
        cursor = body.get("next_cursor")
        if not body.get("has_more"):
            break
    return ToolOutput(content=_clip("\n".join(lines) or "(empty page)"), summary="Read Notion page")


def _blocks(markdown: str) -> list:
    out = []
    for line in (markdown or "").splitlines()[:100]:
        line = line.rstrip()
        if not line.strip():
            continue
        kind, text = "paragraph", line
        for mark, k in (("### ", "heading_3"), ("## ", "heading_2"), ("# ", "heading_1"), ("- ", "bulleted_list_item"),
                        ("* ", "bulleted_list_item"), ("> ", "quote")):
            if line.lstrip().startswith(mark):
                kind, text = k, line.lstrip()[len(mark):]
                break
        text = text.replace("**", "")[:1900]
        out.append({"object": "block", "type": kind, kind: {"rich_text": [{"type": "text", "text": {"content": text}}]}})
    return out


async def _notion_add(ctx: ToolContext, args: dict) -> ToolOutput:
    token = await _token(ctx, "notion")
    parent = (args.get("parent_page_id") or "").strip().replace("-", "")
    title = (args.get("title") or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{32}", parent) or not title:
        raise ValueError("'parent_page_id' (from notion_search) and 'title' are required")
    made = await _post("https://api.notion.com/v1/pages", token, {
        "parent": {"page_id": parent}, "properties": {"title": {"title": [{"text": {"content": title[:200]}}]}},
        "children": _blocks(args.get("content") or "")}, NH)
    return ToolOutput(content=f"Made the Notion page \"{title}\": {made.get('url', '')}", summary=f"Added {title}")


# ---------------------------------------------------------------- messaging
async def _send_message(ctx: ToolContext, args: dict) -> ToolOutput:
    channel = (args.get("app") or "").strip().lower()
    if channel not in connectors.MESSAGING or channel not in ctx.connected:
        linked = [c for c in connectors.MESSAGING if c in ctx.connected]
        raise ValueError(f"'app' must be one of the connected apps: {', '.join(linked) or 'none'}")
    text = (args.get("text") or "").strip()
    if not text:
        raise ValueError("'text' is required")
    await connectors.send(ctx.user_id, channel, text)
    return ToolOutput(content=f"Sent to the user's {connectors.CONNECTORS[channel]['name']}.",
                      summary=f"Sent to {connectors.CONNECTORS[channel]['name']}")


def _obj(props: dict, required: list) -> dict:
    return {"type": "object", "properties": props, "required": required}


S = {"type": "string"}
I = {"type": "integer"}


def register_tools(registry: ToolRegistry):
    tools = [
        Tool("drive_search", "Search the user's Google Drive by file name or words inside files. Leave 'query' "
             "empty to list recent files. Then drive_read a file by its id.",
             _obj({"query": S, "max_results": I}, []), _drive_search, label="Search Google Drive", connector="google_drive"),
        Tool("drive_read", "Read a Google Drive file's text (Docs, Sheets as CSV, Slides, PDF, Word, Excel).",
             _obj({"file_id": S}, ["file_id"]), _drive_read, label="Read Drive file", connector="google_drive"),
        Tool("calendar_events", "List events on the user's Google Calendar, from today (or from_date YYYY-MM-DD) "
             "for 'days' days, optionally matching 'query'.",
             _obj({"days": I, "from_date": S, "query": S}, []), _calendar_events, label="Check calendar",
             connector="google_calendar"),
        Tool("calendar_add", "Add an event or reminder to the user's Google Calendar. 'start' is YYYY-MM-DDTHH:MM:SS "
             "local time, or YYYY-MM-DD for all day. Default length 60 minutes, time zone Asia/Kolkata.",
             _obj({"title": S, "start": S, "end": S, "minutes": I, "timezone": S, "location": S, "description": S,
                   "reminder_minutes": I}, ["title", "start"]), _calendar_add, label="Add to calendar",
             connector="google_calendar"),
        Tool("gmail_search", "Search the user's Gmail with Gmail search words (e.g. 'is:unread', 'from:bank "
             "newer_than:7d'). Returns ids, senders, subjects and previews.",
             _obj({"query": S, "max_results": I}, []), _gmail_search, label="Search Gmail", connector="gmail"),
        Tool("gmail_read", "Read one email in full by its id from gmail_search.",
             _obj({"message_id": S}, ["message_id"]), _gmail_read, label="Read email", connector="gmail"),
        Tool("gmail_draft", "Write an email as a DRAFT in the user's Gmail (it is never sent; the user sends it). "
             "Give thread_id to reply in a thread.",
             _obj({"to": S, "subject": S, "body": S, "thread_id": S}, ["to", "body"]), _gmail_draft,
             label="Draft email", connector="gmail"),
        Tool("github_repos", "List the user's GitHub repositories.", _obj({}, []), _github_repos,
             label="List repositories", connector="github"),
        Tool("github_read", "Read a file, or list a folder, in one of the user's GitHub repositories.",
             _obj({"repo": {"type": "string", "description": "owner/name"}, "path": S}, ["repo"]), _github_read,
             label="Read GitHub", connector="github"),
        Tool("github_issue", "Open an issue in one of the user's GitHub repositories (only when they ask).",
             _obj({"repo": S, "title": S, "body": S}, ["repo", "title"]), _github_issue, label="Open issue",
             connector="github"),
        Tool("notion_search", "Search the Notion pages the user shared with Krish. Empty query lists them.",
             _obj({"query": S}, []), _notion_search, label="Search Notion", connector="notion"),
        Tool("notion_read", "Read a Notion page's content by its id.", _obj({"page_id": S}, ["page_id"]),
             _notion_read, label="Read Notion page", connector="notion"),
        Tool("notion_add_page", "Make a new Notion page under a page the user shared (find it with notion_search). "
             "'content' is simple Markdown: headings, - bullets, > quotes, paragraphs.",
             _obj({"parent_page_id": S, "title": S, "content": S}, ["parent_page_id", "title"]), _notion_add,
             label="Add Notion page", connector="notion"),
    ]
    for tool in tools:
        registry.register(tool)
    for cid in connectors.MESSAGING:
        # One send tool, offered when any messaging app is connected: registered per app so the gate is simple.
        registry.register(Tool(f"send_to_{cid}", f"Send a message to the user's own {connectors.CONNECTORS[cid]['name']} "
                               f"(only when they ask, e.g. 'send this to my {connectors.CONNECTORS[cid]['name']}').",
                               _obj({"text": S}, ["text"]),
                               (lambda c: lambda ctx, args: _send_message(ctx, {**args, "app": c}))(cid),
                               label=f"Send to {connectors.CONNECTORS[cid]['name']}", connector=cid))
