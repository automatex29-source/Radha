"""A built-in backend for apps made in the App Builder: a document database and user accounts.

Pages served by RADHA (preview and published sites) get a small `RADHA` client (see SDK below):

  await RADHA.auth.signup(email, password, name)   await RADHA.auth.login(email, password)
  RADHA.auth.user / RADHA.auth.logout()
  await RADHA.db.list("posts", { mine: true })     await RADHA.db.add("posts", {...}, { private: true })
  await RADHA.db.update("posts", id, {...})        await RADHA.db.remove("posts", id)

The data belongs to the app, not to a RADHA user, and published sites are public, so anyone
who opens the app can call these endpoints. Rules: a document created by a signed-in user can
only be changed or deleted by that user, and a private one is only visible to them. Sizes are
capped to protect the shared (free-tier) database.

Storage (MongoDB):  appdata_docs {appId, collection, id, data, ownerId, private, createdAt, updatedAt}
                    appdata_users {appId, id, email, name, passwordHash, createdAt}
"""
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import JWT_ALGORITHM, _secret, hash_password, verify_password

router = APIRouter(prefix="/api/appdata")
db = None

MAX_DOCS = 5000
MAX_DOC_BYTES = 32 * 1024
MAX_USERS = 1000
LIST_LIMIT = 500
TOKEN_DAYS = 30
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SDK = """<script>(function(){var A=%s,B=new URL(location.href).origin+"/api/appdata/"+A,K="radha-user-"+A,T=null,U=null;
try{var s=JSON.parse(localStorage.getItem(K)||"null");if(s){T=s.token;U=s.user}}catch(e){}
function keep(){try{T?localStorage.setItem(K,JSON.stringify({token:T,user:U})):localStorage.removeItem(K)}catch(e){}}
async function call(m,p,b){var h={"Content-Type":"application/json"};if(T)h.Authorization="Bearer "+T;
var r=await fetch(B+p,{method:m,headers:h,body:b===undefined?undefined:JSON.stringify(b)});var j=null;try{j=await r.json()}catch(e){}
if(!r.ok)throw new Error((j&&j.detail&&(j.detail.msg||j.detail))||("Request failed ("+r.status+")"));return j}
function signed(r){T=r.token;U=r.user;keep();return U}
var auth={get user(){return U},signup:function(e,p,n){return call("POST","/auth/signup",{email:e,password:p,name:n||""}).then(signed)},
login:function(e,p){return call("POST","/auth/login",{email:e,password:p}).then(signed)},logout:function(){T=null;U=null;keep()}};
var q=function(c){return "/db/"+encodeURIComponent(c)};
var dbApi={list:function(c,o){return call("GET",q(c)+(o&&o.mine?"?mine=1":""))},get:function(c,id){return call("GET",q(c)+"/"+encodeURIComponent(id))},
add:function(c,d,o){return call("POST",q(c),{data:d,private:!!(o&&o.private)})},update:function(c,id,d){return call("PATCH",q(c)+"/"+encodeURIComponent(id),{data:d})},
remove:function(c,id){return call("DELETE",q(c)+"/"+encodeURIComponent(id))}};
window.RADHA={appId:A,auth:auth,db:dbApi};})();</script>"""


def init(database):
    global db
    db = database


async def ensure_indexes():
    await db.appdata_docs.create_index([("appId", 1), ("collection", 1), ("createdAt", -1)])
    await db.appdata_docs.create_index([("appId", 1), ("id", 1)], unique=True)
    await db.appdata_users.create_index([("appId", 1), ("email", 1)], unique=True)


def sdk_script(app_id: str) -> str:
    return SDK % json.dumps(app_id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _app(app_id: str) -> dict:
    app = await db.apps.find_one({"id": app_id}, {"id": 1})
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app


def _collection(name: str) -> str:
    if not _NAME_RE.match(name or ""):
        raise HTTPException(status_code=400, detail="Collection names use letters, numbers, - and _ (max 40)")
    return name


def _token(app_id: str, user: dict) -> str:
    payload = {"sub": user["id"], "app": app_id, "type": "appuser",
               "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS)}
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def _viewer(request: Request, app_id: str) -> Optional[str]:
    """The signed-in app user's id, or None for anonymous visitors."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(header[7:], _secret(), algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Your session expired. Please log in again.")
    if payload.get("type") != "appuser" or payload.get("app") != app_id:
        raise HTTPException(status_code=401, detail="Invalid session")
    return payload["sub"]


def _public_user(u: dict) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u.get("name") or ""}


def _public_doc(d: dict) -> dict:
    return {"id": d["id"], "data": d["data"], "ownerId": d.get("ownerId"), "private": d.get("private", False),
            "createdAt": d["createdAt"], "updatedAt": d["updatedAt"]}


def _check_size(data) -> None:
    if len(json.dumps(data)) > MAX_DOC_BYTES:
        raise HTTPException(status_code=413, detail=f"Document too large (max {MAX_DOC_BYTES // 1024} KB)")


# ------------------------------------------------------------------ accounts
class SignupIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(min_length=6, max_length=200)
    name: str = Field(default="", max_length=100)


class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


@router.post("/{app_id}/auth/signup")
async def signup(app_id: str, body: SignupIn):
    await _app(app_id)
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    if await db.appdata_users.find_one({"appId": app_id, "email": email}, {"_id": 1}):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    if await db.appdata_users.count_documents({"appId": app_id}) >= MAX_USERS:
        raise HTTPException(status_code=403, detail="This app has reached its user limit")
    user = {"appId": app_id, "id": str(uuid.uuid4()), "email": email, "name": body.name.strip(),
            "passwordHash": hash_password(body.password), "createdAt": _now()}
    await db.appdata_users.insert_one(user)
    return {"token": _token(app_id, user), "user": _public_user(user)}


@router.post("/{app_id}/auth/login")
async def login(app_id: str, body: LoginIn):
    user = await db.appdata_users.find_one({"appId": app_id, "email": body.email.strip().lower()})
    if not user or not verify_password(body.password, user.get("passwordHash", "")):
        raise HTTPException(status_code=401, detail="Wrong email or password")
    return {"token": _token(app_id, user), "user": _public_user(user)}


@router.get("/{app_id}/auth/me")
async def me(app_id: str, request: Request):
    uid = _viewer(request, app_id)
    user = uid and await db.appdata_users.find_one({"appId": app_id, "id": uid})
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    return _public_user(user)


# ------------------------------------------------------------------ documents
class DocIn(BaseModel):
    data: dict
    private: bool = False


class DocPatch(BaseModel):
    data: dict


def _visible(uid: Optional[str]) -> dict:
    return {"$or": [{"private": {"$ne": True}}, {"ownerId": uid}]} if uid else {"private": {"$ne": True}}


@router.get("/{app_id}/db/{collection}")
async def list_docs(app_id: str, collection: str, request: Request, mine: bool = Query(False)):
    uid = _viewer(request, app_id)
    query = {"appId": app_id, "collection": _collection(collection), **_visible(uid)}
    if mine:
        if not uid:
            raise HTTPException(status_code=401, detail="Log in to see your items")
        query["ownerId"] = uid
    docs = await db.appdata_docs.find(query).sort("createdAt", -1).to_list(LIST_LIMIT)
    return [_public_doc(d) for d in docs]


@router.get("/{app_id}/db/{collection}/{doc_id}")
async def get_doc(app_id: str, collection: str, doc_id: str, request: Request):
    uid = _viewer(request, app_id)
    doc = await db.appdata_docs.find_one({"appId": app_id, "collection": _collection(collection), "id": doc_id, **_visible(uid)})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return _public_doc(doc)


@router.post("/{app_id}/db/{collection}")
async def add_doc(app_id: str, collection: str, body: DocIn, request: Request):
    await _app(app_id)
    uid = _viewer(request, app_id)
    _check_size(body.data)
    if body.private and not uid:
        raise HTTPException(status_code=401, detail="Log in to save private items")
    if await db.appdata_docs.count_documents({"appId": app_id}) >= MAX_DOCS:
        raise HTTPException(status_code=403, detail="This app's database is full")
    ts = _now()
    doc = {"appId": app_id, "collection": _collection(collection), "id": str(uuid.uuid4()), "data": body.data,
           "ownerId": uid, "private": body.private, "createdAt": ts, "updatedAt": ts}
    await db.appdata_docs.insert_one(doc)
    return _public_doc(doc)


async def _owned(app_id: str, collection: str, doc_id: str, uid: Optional[str]) -> dict:
    doc = await db.appdata_docs.find_one({"appId": app_id, "collection": _collection(collection), "id": doc_id, **_visible(uid)})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    if doc.get("ownerId") and doc["ownerId"] != uid:
        raise HTTPException(status_code=403, detail="Only the person who created this can change it")
    return doc


@router.patch("/{app_id}/db/{collection}/{doc_id}")
async def update_doc(app_id: str, collection: str, doc_id: str, body: DocPatch, request: Request):
    uid = _viewer(request, app_id)
    doc = await _owned(app_id, collection, doc_id, uid)
    data = {**doc["data"], **body.data}
    _check_size(data)
    doc.update(data=data, updatedAt=_now())
    await db.appdata_docs.update_one({"_id": doc["_id"]}, {"$set": {"data": data, "updatedAt": doc["updatedAt"]}})
    return _public_doc(doc)


@router.delete("/{app_id}/db/{collection}/{doc_id}")
async def delete_doc(app_id: str, collection: str, doc_id: str, request: Request):
    doc = await _owned(app_id, collection, doc_id, _viewer(request, app_id))
    await db.appdata_docs.delete_one({"_id": doc["_id"]})
    return {"ok": True}


async def delete_app_data(app_id: str):
    await db.appdata_docs.delete_many({"appId": app_id})
    await db.appdata_users.delete_many({"appId": app_id})
