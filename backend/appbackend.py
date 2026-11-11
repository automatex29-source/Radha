"""A real backend for App Builder apps: data rules, an admin role and the app's own server code.

appdata.py gives every app a database and accounts that the page uses straight from the browser. That is
enough for a to-do list, but not for a shop or a booking app: any visitor could change a price, a form
could save half an order, and nothing on the server could check stock or a time slot. So an app can add:

backend.json   the data model and its rules, enforced by the server on every RADHA.db call:
    {
      "admins": ["owner@shop.com"],
      "collections": {
        "products": {"read": "anyone", "create": "admin", "update": "admin", "delete": "admin",
                     "fields": {"name": {"type": "string", "required": true, "max": 80},
                                "price": {"type": "number", "required": true, "min": 0},
                                "category": {"type": "string", "options": ["cakes", "pastries"]}}},
        "orders": {"read": "owner", "create": "nobody", "update": "admin", "delete": "admin",
                   "fields": {"product": {"type": "ref", "to": "products", "required": true},
                              "phone": {"type": "phone", "required": true, "hidden": true}}}
      }
    }
    Who: anyone, signed-in, owner (the person who created the item), admin, nobody (server code only).
    Field types: string, text, number, integer, boolean, email, phone, date, url, ref, list, object, any;
    with required, default, min, max, options, unique and hidden (only its owner and admins see it).
    "extra": false on a collection refuses fields that aren't listed.

api/<name>.js  server code the page calls with `await RADHA.api("name", input)`:
    export default async function (input, ctx) {
      const product = await ctx.db.get("products", input.productId);
      if (!product) ctx.fail("That cake is sold out", 404);
      return ctx.db.add("orders", {product: product.id, total: product.data.price * input.qty, ...});
    }
    It runs on the server in a sandbox (no network, CPU and time limits) with ctx.user, ctx.isAdmin,
    ctx.db (list, get, find, count, add, update, remove: full access, but fields are still checked),
    ctx.ai, ctx.notify, ctx.fetch, ctx.fail(message, status), ctx.requireUser() and ctx.requireAdmin().
    `export const examples = [{...}]` gives test inputs: the App Builder runs each one before it shows the app.

Admins are the emails in "admins", the app owner's own Krish AI email, and app users the owner made admin
in the Data tab. The preview runs the working copy; the published site runs the published version.
"""
import hashlib
import json
import logging
import re
import shutil
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agent import sandbox

logger = logging.getLogger("radha.appbackend")

router = APIRouter(prefix="/api/appdata")
db = None

RULES_FILE = "backend.json"
API_DIR = "api/"
WHO = ("anyone", "signed-in", "owner", "admin", "nobody")
ACTIONS = ("read", "create", "update", "delete")
DEFAULT_WHO = {"read": "anyone", "create": "anyone", "update": "owner", "delete": "owner"}
TYPES = ("string", "text", "number", "integer", "boolean", "email", "phone", "date", "url", "ref", "list",
         "object", "any")
FUNCTION_SECONDS = 10
MAX_CALLS = 100
TEST_SUFFIX = "~test"  # server-code tests write to this copy of the app's data, never to the real one
_RUNNER = (Path(__file__).parent / "app_kit" / "function-runner.mjs").read_text()
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_FN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,59}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)
_API_CALL_RE = re.compile(r"RADHA\.api\(\s*[\"'`]([^\"'`]+)[\"'`]")
_DB_CALL_RE = re.compile(r"RADHA\.db\.(?:list|get|add|update|remove|watch)\(\s*[\"'`]([A-Za-z0-9_-]+)[\"'`]")
_parsed: Dict[str, Tuple[Optional[dict], List[str]]] = {}


def init(database):
    global db
    db = database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ backend.json
def parse_rules(text: str) -> Tuple[Optional[dict], List[str]]:
    """backend.json -> (rules, problems). Rules come back normalised; problems are said so the builder can fix them."""
    key = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()
    if key in _parsed:
        return _parsed[key]
    problems: List[str] = []
    try:
        raw = json.loads(text)
    except ValueError as exc:
        out = (None, [f"{RULES_FILE} is not valid JSON ({exc})"])
        _parsed[key] = out
        return out
    if not isinstance(raw, dict):
        return None, [f"{RULES_FILE} must be a JSON object with \"collections\""]
    admins = [str(a).strip().lower() for a in raw.get("admins") or [] if isinstance(a, str)]
    collections = {}
    for name, spec in (raw.get("collections") or {}).items():
        if not _NAME_RE.match(str(name)):
            problems.append(f"{RULES_FILE}: collection name '{name}' can only use letters, numbers, - and _")
            continue
        if not isinstance(spec, dict):
            problems.append(f"{RULES_FILE}: collection '{name}' must be an object")
            continue
        rule = {"extra": spec.get("extra", True) is not False, "fields": {}}
        for action in ACTIONS:
            who = str(spec.get(action, DEFAULT_WHO[action])).strip().lower().replace("signed_in", "signed-in")
            if who not in WHO:
                problems.append(f"{RULES_FILE}: {name}.{action} is '{who}'; use one of {', '.join(WHO)}")
                who = DEFAULT_WHO[action]
            rule[action] = who
        for field, fspec in (spec.get("fields") or {}).items():
            if isinstance(fspec, str):
                fspec = {"type": fspec}
            if not isinstance(fspec, dict):
                problems.append(f"{RULES_FILE}: {name}.fields.{field} must be an object like {{\"type\": \"string\"}}")
                continue
            ftype = str(fspec.get("type", "any")).lower()
            if ftype not in TYPES:
                problems.append(f"{RULES_FILE}: {name}.fields.{field} has type '{ftype}'; use one of {', '.join(TYPES)}")
                ftype = "any"
            if ftype == "ref" and fspec.get("to") not in (raw.get("collections") or {}):
                problems.append(f"{RULES_FILE}: {name}.fields.{field} is a ref, so \"to\" must name another collection")
            rule["fields"][str(field)] = {**fspec, "type": ftype}
        collections[str(name)] = rule
    out = ({"admins": admins, "collections": collections, "strict": raw.get("strict") is True}, problems)
    if len(_parsed) > 2000:
        _parsed.clear()
    _parsed[key] = out
    return out


async def _file(app_id: str, path: str, draft: bool) -> Optional[str]:
    """One file of the app: the working copy for the preview, otherwise the published version (or the working
    copy when the app isn't published yet)."""
    app = await db.apps.find_one({"id": app_id}, {"published": 1})
    commit_id = ((app or {}).get("published") or {}).get("commitId")
    if not draft and commit_id:
        version = await db.app_commits.find_one({"appId": app_id, "id": commit_id}, {"files": 1})
        digest = (version or {}).get("files", {}).get(path)
        if not digest:
            return None
        blob = await db.app_blobs.find_one({"hash": digest}, {"content": 1})
        return blob["content"] if blob else None
    doc = await db.app_files.find_one({"appId": app_id, "path": path}, {"content": 1})
    return doc["content"] if doc else None


async def rules_for(app_id: str, draft: bool) -> Optional[dict]:
    text = await _file(app_id, RULES_FILE, draft)
    if text is None:
        return None
    return parse_rules(text)[0]


def is_draft(request: Request) -> bool:
    return request.headers.get("X-Radha-Draft") == "1"


def collection_rule(rules: Optional[dict], collection: str) -> Optional[dict]:
    """The collection's rules, None when backend.json doesn't list it (the simple built-in rules apply)."""
    if not rules:
        return None
    rule = rules["collections"].get(collection)
    if rule is None and rules.get("strict"):
        raise HTTPException(status_code=403, detail=f"This app doesn't store '{collection}'")
    return rule


# ------------------------------------------------------------------ who is asking
async def viewer(app_id: str, uid: Optional[str], rules: Optional[dict]) -> Optional[dict]:
    """The signed-in app user as {id, email, name, isAdmin}, or None."""
    if not uid:
        return None
    user = await db.appdata_users.find_one({"appId": app_id, "id": uid})
    if not user:
        return None
    return {"id": uid, "email": user["email"], "name": user.get("name") or "",
            "isAdmin": await is_admin(app_id, user, rules)}


async def is_admin(app_id: str, user: dict, rules: Optional[dict]) -> bool:
    if user.get("role") == "admin":
        return True
    email = (user.get("email") or "").lower()
    if rules and email in rules["admins"]:
        return True
    app = await db.apps.find_one({"id": app_id}, {"userId": 1})
    owner = app and app.get("userId") and await db.users.find_one({"id": app["userId"]}, {"email": 1})
    return bool(owner and (owner.get("email") or "").lower() == email)


def allowed(rule: dict, action: str, who: Optional[dict], doc: Optional[dict] = None) -> None:
    """Raise when `who` may not do `action` (for update and delete, on `doc`)."""
    need = rule[action]
    if who and who["isAdmin"]:
        return
    if need == "anyone":
        return
    if need == "nobody":
        raise HTTPException(status_code=403, detail="This can only be changed by the app itself")
    if not who:
        raise HTTPException(status_code=401, detail="Please log in first")
    if need == "admin":
        raise HTTPException(status_code=403, detail="Only the app's admins can do this")
    if need == "owner" and doc is not None and doc.get("ownerId") != who["id"]:
        raise HTTPException(status_code=403, detail="Only the person who created this can change it")


def read_filter(rule: dict, who: Optional[dict]) -> dict:
    """Extra query terms so a reader only gets what the read rule lets them see."""
    need = rule["read"]
    if need == "anyone" or (who and who["isAdmin"]):
        return {}
    if need == "nobody":
        raise HTTPException(status_code=403, detail="This data is private")
    if not who:
        raise HTTPException(status_code=401, detail="Please log in to see this")
    if need == "admin":
        raise HTTPException(status_code=403, detail="Only the app's admins can see this")
    return {"ownerId": who["id"]} if need == "owner" else {}


def strip_hidden(rule: Optional[dict], doc: dict, who: Optional[dict]) -> dict:
    """A public document without its hidden fields, unless the reader owns it or is an admin."""
    if not rule or (who and (who["isAdmin"] or who["id"] == doc.get("ownerId"))):
        return doc
    hidden = [f for f, spec in rule["fields"].items() if spec.get("hidden")]
    if hidden:
        doc = {**doc, "data": {k: v for k, v in doc["data"].items() if k not in hidden}}
    return doc


# ------------------------------------------------------------------ field checks
def _label(field: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])|_", " ", field).strip().capitalize()


def _value(field: str, spec: dict, value: Any) -> Any:
    """The value checked (and tidied: "12" -> 12 for a number); raise a readable error when it's wrong."""
    ftype, name = spec["type"], _label(field)
    bad = lambda what: HTTPException(status_code=400, detail=f"{name} {what}")  # noqa: E731
    if ftype in ("string", "text", "email", "phone", "url", "date", "ref"):
        if isinstance(value, (int, float)) and not isinstance(value, bool) and ftype in ("string", "text", "phone"):
            value = str(value)
        if not isinstance(value, str):
            raise bad("must be text")
        value = value.strip()
        if ftype == "email":
            value = value.lower()
            if not _EMAIL_RE.match(value):
                raise bad("must be a valid email address")
        elif ftype == "phone":
            digits = re.sub(r"[\s\-().]", "", value)
            if not re.fullmatch(r"\+?\d{7,15}", digits):
                raise bad("must be a valid phone number")
        elif ftype == "url" and not _URL_RE.match(value):
            raise bad("must be a link starting with http:// or https://")
        elif ftype == "date":
            try:
                (datetime.fromisoformat(value.replace("Z", "+00:00")) if "T" in value else date.fromisoformat(value))
            except ValueError:
                raise bad("must be a date like 2026-01-31")
        limit = spec.get("max", 200 if ftype == "string" else 5000)
        if isinstance(limit, int) and len(value) > limit:
            raise bad(f"can be at most {limit} characters")
        if isinstance(spec.get("min"), int) and len(value) < spec["min"]:
            raise bad(f"needs at least {spec['min']} characters")
    elif ftype in ("number", "integer"):
        if isinstance(value, str) and re.fullmatch(r"\s*-?\d+(\.\d+)?\s*", value):
            value = float(value) if "." in value else int(value)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise bad("must be a number")
        if ftype == "integer":
            if float(value) != int(value):
                raise bad("must be a whole number")
            value = int(value)
        if isinstance(spec.get("min"), (int, float)) and value < spec["min"]:
            raise bad(f"must be at least {spec['min']}")
        if isinstance(spec.get("max"), (int, float)) and value > spec["max"]:
            raise bad(f"can be at most {spec['max']}")
    elif ftype == "boolean":
        if isinstance(value, str) and value.lower() in ("true", "false", "on", "off", "yes", "no", "1", "0"):
            value = value.lower() in ("true", "on", "yes", "1")
        if not isinstance(value, bool):
            raise bad("must be true or false")
    elif ftype == "list":
        if not isinstance(value, list):
            raise bad("must be a list")
        if isinstance(spec.get("max"), int) and len(value) > spec["max"]:
            raise bad(f"can have at most {spec['max']} items")
    elif ftype == "object" and not isinstance(value, dict):
        raise bad("must be an object")
    options = spec.get("options")
    if isinstance(options, list) and options and value not in options:
        raise bad(f"must be one of: {', '.join(str(o) for o in options)}")
    return value


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or value == []


async def check_data(app_id: str, collection: str, rule: Optional[dict], data: dict, old: Optional[dict] = None,
                     doc_id: Optional[str] = None) -> dict:
    """The document's data after the collection's field rules: defaults filled in, values tidied, and a
    readable 400 for the first thing that's wrong. `old` is the stored data when this is an update."""
    if not rule:
        return {**(old or {}), **data}
    fields = rule["fields"]
    if not rule["extra"]:
        unknown = [k for k in data if k not in fields]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown field '{unknown[0]}' for {collection}")
    merged = {**(old or {}), **data}
    if old is None:
        for field, spec in fields.items():
            if field not in merged and "default" in spec:
                merged[field] = spec["default"]
    for field, spec in fields.items():
        value = merged.get(field)
        if _empty(value):
            if spec.get("required"):
                raise HTTPException(status_code=400, detail=f"{_label(field)} is required")
            continue
        if old is not None and field not in data:
            continue  # unchanged on an update
        value = _value(field, spec, value)
        merged[field] = value
        if spec["type"] == "ref":
            target = spec.get("to")
            if not await db.appdata_docs.find_one({"appId": app_id, "collection": target, "id": value}, {"_id": 1}):
                raise HTTPException(status_code=400, detail=f"{_label(field)} doesn't match any {target}")
        if spec.get("unique"):
            query = {"appId": app_id, "collection": collection, f"data.{field}": value}
            if doc_id:
                query["id"] = {"$ne": doc_id}
            if await db.appdata_docs.find_one(query, {"_id": 1}):
                raise HTTPException(status_code=409, detail=f"That {_label(field).lower()} is already taken")
    return merged


# ------------------------------------------------------------------ server code (api/<name>.js)
def function_path(files: Dict[str, str], name: str) -> Optional[str]:
    for ext in (".js", ".mjs"):
        if f"{API_DIR}{name}{ext}" in files:
            return f"{API_DIR}{name}{ext}"
    return None


def function_names(files: Dict[str, str]) -> List[str]:
    names = []
    for path in files:
        if path.startswith(API_DIR) and path.endswith((".js", ".mjs")) and path.count("/") == 1:
            name = path[len(API_DIR):].rsplit(".", 1)[0]
            if _FN_RE.match(name) and not name.startswith("_"):
                names.append(name)
    return sorted(names)


async def _code_files(app_id: str, draft: bool) -> Dict[str, str]:
    """The app's JavaScript and JSON files (what server code can import), from the version that runs."""
    app = await db.apps.find_one({"id": app_id}, {"published": 1})
    commit_id = ((app or {}).get("published") or {}).get("commitId")
    if not draft and commit_id:
        version = await db.app_commits.find_one({"appId": app_id, "id": commit_id}, {"files": 1})
        hashes = {p: h for p, h in ((version or {}).get("files") or {}).items() if p.endswith((".js", ".mjs", ".json"))}
        blobs = {b["hash"]: b["content"] async for b in db.app_blobs.find({"hash": {"$in": list(set(hashes.values()))}})}
        return {p: blobs[h] for p, h in hashes.items() if h in blobs}
    return {f["path"]: f["content"] async for f in db.app_files.find(
        {"appId": app_id, "path": {"$regex": r"\.(m?js|json)$"}}, {"path": 1, "content": 1})}


class _Services:
    """What a server function's ctx can reach, for one request. Database calls work on `data_app` (the app's
    id, or its test copy) with full access: the code is the app owner's, so only field rules apply."""

    def __init__(self, app_id: str, data_app: str, rules: Optional[dict], who: Optional[dict],
                 request: Optional[Request], test: bool):
        self.app_id, self.data_app, self.rules, self.who, self.request, self.test = app_id, data_app, rules, who, request, test

    def _rule(self, collection: str) -> Optional[dict]:
        if not _NAME_RE.match(str(collection or "")):
            raise sandbox.RpcError("Collection names use letters, numbers, - and _ (max 40)")
        return (self.rules or {}).get("collections", {}).get(collection)

    async def handle(self, op: str, args: list):
        try:
            return await self._handle(op, args)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
            raise sandbox.RpcError(detail, exc.status_code)

    async def _handle(self, op: str, args: list):
        import appdata  # here: appdata imports this module
        pad = list(args) + [None, None, None]
        if op in ("list", "find", "count", "get", "add", "update", "remove"):
            collection = str(pad[0] or "")
            rule = self._rule(collection)
            base = {"appId": self.data_app, "collection": collection}
            if op in ("list", "find", "count"):
                opts = pad[1] if isinstance(pad[1], dict) else {}
                where = opts.get("where", opts) if op == "list" else opts
                query = {**base, **appdata._where(json.dumps({k: v for k, v in (where or {}).items()
                                                              if k not in ("limit", "oldest", "mine", "where")}))}
                if op == "list" and opts.get("mine"):
                    query["ownerId"] = (self.who or {}).get("id") or "-"
                if op == "count":
                    return await db.appdata_docs.count_documents(query)
                limit = max(1, min(int(opts.get("limit") or appdata.LIST_LIMIT), appdata.LIST_LIMIT)) if op == "list" else appdata.LIST_LIMIT
                docs = await db.appdata_docs.find(query).sort("createdAt", 1 if opts.get("oldest") else -1).limit(limit).to_list(limit)
                return [appdata._public_doc(d) for d in docs]
            if op == "get":
                doc = await db.appdata_docs.find_one({**base, "id": str(pad[1] or "")})
                return appdata._public_doc(doc) if doc else None
            if op == "add":
                if not isinstance(pad[1], dict):
                    raise sandbox.RpcError("db.add needs an object of data")
                data = await check_data(self.data_app, collection, rule, pad[1])
                appdata._check_size(data)
                if await db.appdata_docs.count_documents({"appId": self.data_app}) >= appdata.MAX_DOCS:
                    raise sandbox.RpcError("This app's database is full", 403)
                opts = pad[2] if isinstance(pad[2], dict) else {}
                ts = _now()
                doc = {**base, "id": str(uuid.uuid4()), "data": data, "ownerId": (self.who or {}).get("id"),
                       "private": bool(opts.get("private")), "createdAt": ts, "updatedAt": ts}
                await db.appdata_docs.insert_one(doc)
                return appdata._public_doc(doc)
            doc = await db.appdata_docs.find_one({**base, "id": str(pad[1] or "")})
            if not doc:
                raise sandbox.RpcError(f"No {collection} item with id {pad[1]}", 404)
            if op == "remove":
                await db.appdata_docs.delete_one({"_id": doc["_id"]})
                return True
            if not isinstance(pad[2], dict):
                raise sandbox.RpcError("db.update needs an object of data")
            data = await check_data(self.data_app, collection, rule, pad[2], old=doc["data"], doc_id=doc["id"])
            appdata._check_size(data)
            doc.update(data=data, updatedAt=_now())
            await db.appdata_docs.update_one({"_id": doc["_id"]}, {"$set": {"data": data, "updatedAt": doc["updatedAt"]}})
            return appdata._public_doc(doc)
        if op in ("ai", "notify", "fetch") and self.test:
            return {"ai": "A sample answer from the AI.", "notify": {"ok": True},
                    "fetch": {"status": 200, "ok": True, "data": None, "text": ""}}[op]
        import appcloud
        if op == "ai":
            opts = pad[1] if isinstance(pad[1], dict) else {}
            body = appcloud.AiIn(prompt=str(pad[0] or "")[:8000] or "-", system=str(opts.get("system") or "")[:3000],
                                 json=bool(opts.get("json")))
            out = await appcloud.app_ai(self.app_id, body, self.request)
            return out.get("data") if opts.get("json") else out.get("text")
        if op == "notify":
            msg = pad[0] if isinstance(pad[0], dict) else {}
            fields = {k: v for k, v in msg.items() if k not in ("subject", "message", "replyTo")}
            body = appcloud.NotifyIn(subject=str(msg.get("subject") or "")[:150],
                                     message=str(msg.get("message") or json.dumps(fields, indent=1))[:5000] or "-",
                                     replyTo=str(msg.get("replyTo") or msg.get("email") or "")[:200], fields=fields)
            return await appcloud.notify(self.app_id, body, self.request)
        if op == "fetch":
            opts = pad[1] if isinstance(pad[1], dict) else {}
            body = appcloud.FetchIn(url=str(pad[0] or ""), method=str(opts.get("method") or "GET").upper(),
                                    headers=opts.get("headers") or {}, body=opts.get("body"))
            return await appcloud.proxy_fetch(self.app_id, body, self.request)
        raise sandbox.RpcError(f"Unknown call {op}")


def node_available() -> bool:
    return bool(shutil.which("node"))


async def run_function(app_id: str, files: Dict[str, str], name: str, input_value: Any, who: Optional[dict],
                       rules: Optional[dict], request: Optional[Request] = None, test: bool = False) -> dict:
    """Run api/<name>.js once. Returns {ok, result} or {ok: False, status, error, stack}, plus the logs."""
    path = function_path(files, name)
    if not path:
        return {"ok": False, "status": 404, "error": f"This app has no server function '{name}'", "logs": ""}
    if not node_available():
        return {"ok": False, "status": 503, "error": "Server code can't run on this server right now", "logs": ""}
    code = {p: c for p, c in files.items() if p.endswith((".js", ".mjs", ".json"))}
    for pkg in ("package.json", API_DIR + "package.json"):
        if pkg not in code:
            code[pkg] = '{"type": "module"}'
    code[".radha/runner.mjs"] = _RUNNER
    services = _Services(app_id, app_id + TEST_SUFFIX if test else app_id, rules, who, request, test)
    start = {"t": "start", "file": path, "input": input_value, "user": who}
    res = await sandbox.run_rpc(["node", ".radha/runner.mjs"], code, start, services.handle,
                                timeout=FUNCTION_SECONDS, max_calls=MAX_CALLS)
    if res.timed_out:
        return {"ok": False, "status": 504, "error": f"{path} took longer than {FUNCTION_SECONDS} seconds", "logs": res.logs}
    if not res.done:
        tail = res.logs.strip().splitlines()[-3:]
        return {"ok": False, "status": 500, "error": f"{path} stopped before it answered" + (": " + " ".join(tail) if tail else ""),
                "logs": res.logs}
    out = {"ok": bool(res.done.get("ok")), "logs": res.logs}
    if out["ok"]:
        out["result"] = res.done.get("result")
    else:
        stack = re.sub(r"file://\S*?/radha-rpc-[^/]+/", "", str(res.done.get("stack") or ""))
        out.update(status=int(res.done.get("status") or 500), error=str(res.done.get("error") or "Failed")[:500],
                   stack=stack)
    return out


class CallIn(BaseModel):
    input: Any = None


@router.post("/{app_id}/api/{name}")
async def call_function(app_id: str, name: str, body: CallIn, request: Request):
    import appcloud
    import appdata
    if not _FN_RE.match(name) or name.startswith("_"):
        raise HTTPException(status_code=404, detail="No such server function")
    await appdata._app(app_id)
    appcloud._limit("api", app_id, request)
    if len(json.dumps(body.input, default=str)) > appdata.MAX_DOC_BYTES:
        raise HTTPException(status_code=413, detail="The request is too large")
    draft = is_draft(request)
    rules = await rules_for(app_id, draft)
    who = await viewer(app_id, appdata._viewer(request, app_id), rules)
    files = await _code_files(app_id, draft)
    out = await run_function(app_id, files, name, body.input, who, rules, request=request)
    if out["ok"]:
        return {"result": out["result"]}
    if out["status"] >= 500:
        logger.warning("app %s function %s failed: %s", app_id, name, out["error"])
        await db.appbackend_errors.insert_one({"appId": app_id, "name": name, "error": out["error"],
                                               "stack": out.get("stack", ""), "logs": out.get("logs", "")[:4000],
                                               "createdAt": _now()})
    raise HTTPException(status_code=out["status"], detail=out["error"] if out["status"] < 500 or draft
                        else "Something went wrong on the server. Please try again.")


# ------------------------------------------------------------------ the builder's backend test
_EXAMPLES_RE = re.compile(r"export\s+const\s+examples\s*=\s*(\[.*?\])\s*;?\s*$", re.DOTALL | re.MULTILINE)


async def _examples(app_id: str, files: Dict[str, str], name: str) -> List[Any]:
    """The function's `export const examples = [...]`, read by running a tiny script in the sandbox."""
    path = function_path(files, name)
    if not path or "examples" not in files[path]:
        return []
    code = {p: c for p, c in files.items() if p.endswith((".js", ".mjs", ".json"))}
    for pkg in ("package.json", API_DIR + "package.json"):
        code.setdefault(pkg, '{"type": "module"}')
    code[".radha/examples.mjs"] = (
        "import { pathToFileURL } from 'node:url'; import path from 'node:path';"
        f"const m = await import(pathToFileURL(path.resolve({json.dumps(path)})).href);"
        "process.stdout.write(JSON.stringify(Array.isArray(m.examples) ? m.examples.slice(0, 5) : []));")
    res = await sandbox.run_shell("node .radha/examples.mjs", code)
    try:
        out = json.loads(res.stdout.strip() or "[]")
        return out if isinstance(out, list) else []
    except ValueError:
        return []


def uses_backend(files: Dict[str, str]) -> bool:
    return RULES_FILE in files or bool(function_names(files)) or any("RADHA.api(" in c for c in files.values())


async def backend_problems(app_id: str, files: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """Test the app's backend the way an engineer would before shipping: backend.json is valid, every
    RADHA.api call has its function, every function runs its examples (and an empty request) without
    crashing, on a throwaway copy of the data. Returns (problems, a line per check that passed)."""
    problems, passed = [], []
    rules = None
    if RULES_FILE in files:
        rules, found = parse_rules(files[RULES_FILE])
        problems += found
        if rules and not found:
            passed.append(f"{RULES_FILE}: {len(rules['collections'])} collections with rules")
    names = function_names(files)
    pages = {p: c for p, c in files.items() if not p.startswith(API_DIR) and p.endswith((".html", ".htm", ".js", ".mjs", ".jsx", ".tsx"))}
    called = {}
    for path, content in pages.items():
        for n in _API_CALL_RE.findall(content):
            called.setdefault(n, path)
    for n, path in sorted(called.items()):
        if n not in names:
            problems.append(f"{path} calls RADHA.api(\"{n}\") but there is no {API_DIR}{n}.js: write it, "
                            "with export default async function (input, ctx)")
    if rules:
        for path, content in pages.items():
            for c in set(_DB_CALL_RE.findall(content)):
                if c not in rules["collections"]:
                    problems.append(f"{path} uses the '{c}' collection but {RULES_FILE} doesn't list it: add it "
                                    "with its fields and who can read and change it")
    if names and not node_available():
        return problems, passed
    data_app = app_id + TEST_SUFFIX
    await db.appdata_docs.delete_many({"appId": data_app})
    if names:  # the tests see a copy of the app's real data, so examples can use real items
        copies = [{**{k: v for k, v in d.items() if k != "_id"}, "appId": data_app}
                  async for d in db.appdata_docs.find({"appId": app_id}).limit(1000)]
        if copies:
            await db.appdata_docs.insert_many(copies)
    try:
        for n in names[:12]:
            source = files[function_path(files, n)]
            if "export default" not in source and "export async function handler" not in source and "export function handler" not in source:
                problems.append(f"{API_DIR}{n}.js must export default async function (input, ctx)")
                continue
            examples = await _examples(app_id, files, n)
            tried = 0
            for example in examples[:3] + [None]:
                out = await run_function(app_id, files, n, example if example is not None else {}, None, rules, test=True)
                tried += 1
                if out["ok"]:
                    continue
                if out["status"] < 500 and (example is None or out["status"] in (404, 409)):
                    continue  # an empty request refused with a clear message is right; "not found" depends on the data
                if example is not None and out["status"] in (401, 403):
                    # the example needs a signed-in user or an admin: try once as a test admin
                    admin = {"id": "test-admin", "email": "admin@example.com", "name": "Test admin", "isAdmin": True}
                    out = await run_function(app_id, files, n, example, admin, rules, test=True)
                    if out["ok"]:
                        continue
                what = f"with input {json.dumps(example)[:160]}" if example is not None else "when the input is empty ({})"
                hint = ("; check the input and call ctx.fail(\"a friendly message\") instead of crashing"
                        if out["status"] >= 500 else "")
                detail = out["error"] + (f" ({out['stack'].splitlines()[1].strip()})" if out.get("stack", "").count("\n") else "")
                problems.append(f"Server function {n} failed {what}: {detail}{hint}")
                break
            else:
                passed.append(f"api/{n}: ran {tried} test request{'s' if tried != 1 else ''}")
            if not examples:
                problems.append(f"{API_DIR}{n}.js has no examples: add export const examples = [{{...}}] with one or "
                                "two realistic inputs so the function can be tested")
    finally:
        await db.appdata_docs.delete_many({"appId": data_app})
    return problems[:8], passed
