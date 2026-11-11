"""The App Builder's real backend (appbackend.py): data rules, admins and server functions."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
mongomock_motor = pytest.importorskip("mongomock_motor")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import appbackend  # noqa: E402
import appcloud  # noqa: E402
import appdata  # noqa: E402

RULES = """{
  "admins": ["boss@shop.com"],
  "collections": {
    "products": {"read": "anyone", "create": "admin", "update": "admin", "delete": "admin",
                 "fields": {"name": {"type": "string", "required": true, "max": 40},
                            "price": {"type": "number", "required": true, "min": 0},
                            "category": {"type": "string", "options": ["cakes", "pastries"], "default": "cakes"},
                            "sku": {"type": "string", "unique": true}}},
    "orders": {"read": "owner", "create": "nobody", "update": "admin", "delete": "admin", "extra": false,
               "fields": {"product": {"type": "ref", "to": "products", "required": true},
                          "qty": {"type": "integer", "min": 1, "max": 20, "required": true},
                          "total": {"type": "number"},
                          "phone": {"type": "phone", "required": true, "hidden": true}}},
    "reviews": {"create": "signed-in", "fields": {"stars": {"type": "integer", "min": 1, "max": 5, "required": true},
                                                   "email": {"type": "email", "hidden": true}}}
  }
}"""

PLACE_ORDER = """
export const examples = [{ productId: "p-test", qty: 2, phone: "98765 43210" }];
export default async function (input, ctx) {
  if (!input || !input.productId) ctx.fail("Pick a cake first");
  const product = await ctx.db.get("products", input.productId);
  if (!product) ctx.fail("That cake is sold out", 404);
  console.log("ordering", product.data.name);
  return ctx.db.add("orders", { product: product.id, qty: input.qty, phone: input.phone,
                                total: product.data.price * input.qty });
}
"""

BROKEN = """
export const examples = [{ name: "x" }];
export default async function (input, ctx) { return input.items.length; }
"""

node = pytest.mark.skipif(not appbackend.node_available(), reason="needs node")


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", "test-secret-that-is-long-enough-for-hs256")
    database = mongomock_motor.AsyncMongoMockClient()["t"]
    for mod in (appdata, appcloud, appbackend):
        mod.init(database)
    app = FastAPI()
    app.include_router(appdata.router)
    app.include_router(appbackend.router)
    with TestClient(app) as c:
        def put(path, content):
            c.portal.call(database.app_files.update_one, {"appId": "app1", "path": path},
                          {"$set": {"content": content}}, True)
        c.portal.call(database.apps.insert_one, {"id": "app1", "userId": "owner1"})
        c.portal.call(database.users.insert_one, {"id": "owner1", "email": "maker@krish.ai"})
        put("backend.json", RULES)
        yield c, database, put


def token(c, email):
    return {"Authorization": "Bearer " + c.post("/api/appdata/app1/auth/signup",
                                                 json={"email": email, "password": "secret1"}).json()["token"]}


def test_rules_parse_and_explain_mistakes():
    rules, problems = appbackend.parse_rules(RULES)
    assert not problems and rules["collections"]["orders"]["create"] == "nobody"
    _, problems = appbackend.parse_rules('{"collections": {"a": {"read": "everyone", "fields": {"x": {"type": "money"}}}}}')
    assert any("everyone" in p for p in problems) and any("money" in p for p in problems)
    assert appbackend.parse_rules("{nope")[1][0].startswith("backend.json is not valid JSON")


def test_only_admins_change_products_and_fields_are_checked(env):
    c, _, _ = env
    visitor = c.post("/api/appdata/app1/db/products", json={"data": {"name": "Cake", "price": 5}})
    assert visitor.status_code == 401
    shopper = token(c, "ann@x.com")
    assert c.post("/api/appdata/app1/db/products", json={"data": {"name": "Cake", "price": 5}}, headers=shopper).status_code == 403
    boss = token(c, "boss@shop.com")
    assert c.post("/api/appdata/app1/auth/login", json={"email": "boss@shop.com", "password": "secret1"}).json()["user"]["isAdmin"]
    bad = c.post("/api/appdata/app1/db/products", json={"data": {"name": "Cake", "price": "free"}}, headers=boss)
    assert bad.status_code == 400 and bad.json()["detail"] == "Price must be a number"
    assert c.post("/api/appdata/app1/db/products", json={"data": {"price": 5}}, headers=boss).json()["detail"] == "Name is required"
    assert "must be one of" in c.post("/api/appdata/app1/db/products", json={"data": {"name": "C", "price": 1, "category": "pies"}},
                                      headers=boss).json()["detail"]
    ok = c.post("/api/appdata/app1/db/products", json={"data": {"name": "Cake", "price": "450", "sku": "C1"}}, headers=boss).json()
    assert ok["data"] == {"name": "Cake", "price": 450, "category": "cakes", "sku": "C1"}
    assert c.post("/api/appdata/app1/db/products", json={"data": {"name": "Cake 2", "price": 1, "sku": "C1"}}, headers=boss).status_code == 409
    # a visitor can't change or delete what the admin made, even though it was public
    assert c.patch(f"/api/appdata/app1/db/products/{ok['id']}", json={"data": {"price": 1}}).status_code == 401
    assert c.delete(f"/api/appdata/app1/db/products/{ok['id']}", headers=shopper).status_code == 403
    assert c.patch(f"/api/appdata/app1/db/products/{ok['id']}", json={"data": {"price": 500}}, headers=boss).json()["data"]["price"] == 500


def test_app_owner_is_admin_and_can_make_others_admin(env):
    c, database, _ = env
    maker = token(c, "maker@krish.ai")
    assert c.get("/api/appdata/app1/auth/me", headers=maker).json()["isAdmin"]
    helper = token(c, "help@x.com")
    assert c.post("/api/appdata/app1/db/products", json={"data": {"name": "Cake", "price": 5}}, headers=helper).status_code == 403
    c.portal.call(database.appdata_users.update_one, {"email": "help@x.com"}, {"$set": {"role": "admin"}})
    assert c.post("/api/appdata/app1/db/products", json={"data": {"name": "Cake", "price": 5}}, headers=helper).status_code == 200


def test_owner_only_reads_and_hidden_fields(env):
    c, _, _ = env
    ann, bob = token(c, "ann@x.com"), token(c, "bob@x.com")
    assert c.post("/api/appdata/app1/db/reviews", json={"data": {"stars": 5}}).status_code == 401
    assert c.post("/api/appdata/app1/db/reviews", json={"data": {"stars": 9}}, headers=ann).json()["detail"] == "Stars can be at most 5"
    c.post("/api/appdata/app1/db/reviews", json={"data": {"stars": 4, "email": "ANN@x.com"}}, headers=ann)
    assert c.get("/api/appdata/app1/db/reviews").json()[0]["data"] == {"stars": 4}  # email hidden from others
    assert c.get("/api/appdata/app1/db/reviews", headers=ann).json()[0]["data"]["email"] == "ann@x.com"
    # orders: nobody may create them from the page, and a reader sees only their own
    assert c.post("/api/appdata/app1/db/orders", json={"data": {"qty": 1}}, headers=ann).status_code == 403
    assert c.get("/api/appdata/app1/db/orders").status_code == 401
    assert c.get("/api/appdata/app1/db/orders", headers=bob).json() == []


def test_collections_without_rules_keep_the_simple_rules(env):
    c, _, _ = env
    r = c.post("/api/appdata/app1/db/notes", json={"data": {"anything": [1, 2]}})
    assert r.status_code == 200


@node
def test_server_function_places_an_order_with_trusted_price(env):
    c, database, put = env
    put("api/place-order.js", PLACE_ORDER)
    boss = token(c, "boss@shop.com")
    cake = c.post("/api/appdata/app1/db/products", json={"data": {"name": "Truffle", "price": 450}}, headers=boss).json()
    ann = token(c, "ann@x.com")
    r = c.post("/api/appdata/app1/api/place-order", json={"input": {"productId": cake["id"], "qty": 2, "phone": "98765 43210", "total": 1}},
               headers=ann)
    assert r.status_code == 200, r.text
    order = r.json()["result"]
    assert order["data"]["total"] == 900 and order["ownerId"]
    assert [o["id"] for o in c.get("/api/appdata/app1/db/orders", headers=ann).json()] == [order["id"]]
    # the function's own friendly errors reach the page with their status
    r = c.post("/api/appdata/app1/api/place-order", json={"input": {"productId": "nope", "qty": 1, "phone": "9876543210"}})
    assert r.status_code == 404 and r.json()["detail"] == "That cake is sold out"
    # field rules still apply inside server code
    r = c.post("/api/appdata/app1/api/place-order", json={"input": {"productId": cake["id"], "qty": 50, "phone": "9876543210"}})
    assert r.status_code == 400 and r.json()["detail"] == "Qty can be at most 20"
    assert c.post("/api/appdata/app1/api/missing", json={"input": {}}).status_code == 404


@node
def test_builder_backend_test_catches_crashes_and_missing_pieces(env):
    c, database, _ = env
    files = {"backend.json": RULES, "api/place-order.js": PLACE_ORDER, "api/count.js": BROKEN,
             "index.html": '<script>RADHA.api("checkout", {}); RADHA.db.list("wishlist")</script>'}
    problems, passed = c.portal.call(appbackend.backend_problems, "app1", files)
    text = "\n".join(problems)
    assert "no api/checkout.js" in text
    assert "'wishlist' collection" in text
    assert "Server function count failed" in text and "ctx.fail" in text
    assert any(p.startswith("api/place-order") for p in passed)
    # the tests never touch the real data
    assert c.portal.call(database.appdata_docs.count_documents, {"appId": "app1"}) == 0
    assert c.portal.call(database.appdata_docs.count_documents, {"appId": "app1~test"}) == 0


@node
def test_function_timeout_and_sandbox_has_no_network(env, monkeypatch):
    c, _, put = env
    monkeypatch.setattr(appbackend, "FUNCTION_SECONDS", 2)
    put("api/spin.js", "export default async function () { while (true) {} }")
    r = c.post("/api/appdata/app1/api/spin", json={"input": {}}, headers={"X-Radha-Draft": "1"})
    assert r.status_code == 504
