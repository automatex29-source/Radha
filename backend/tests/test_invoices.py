"""Invoices: a numbered PDF for every paid order, listed in Settings > Billing and emailed with the PDF attached."""
import asyncio
import base64
import hashlib
import hmac
import os
import sys
import time
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
pytest.importorskip("fpdf")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SECRET = "key-secret"


@pytest.fixture(scope="module")
def client():
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b", RAZORPAY_KEY_ID="rzp_test_abc",
                      RAZORPAY_KEY_SECRET=SECRET, RAZORPAY_WEBHOOK_SECRET="hook")
    import motor.motor_asyncio
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        yield c
    for k in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"):
        os.environ.pop(k, None)


@pytest.fixture(autouse=True)
def fake_razorpay(monkeypatch):
    import billing
    count = {"n": 0}

    async def create(amount, receipt, notes):
        count["n"] += 1
        return {"id": f"order_inv{count['n']}_{receipt[:6]}", "amount": amount}

    monkeypatch.setattr(billing, "_create_razorpay_order", create)


@pytest.fixture
def sent(monkeypatch):
    """Emails 'sent', with their attachments."""
    import mailer
    out = []

    async def send(to, subject, html, text, attachments=None):
        out.append({"to": to, "subject": subject, "html": html, "attachments": attachments or []})

    monkeypatch.setattr(mailer, "send", send)
    monkeypatch.setattr(mailer, "configured", lambda: True)
    return out


def _user(client, email, name="Asha Sharma"):
    r = client.post("/api/auth/register", json={"name": name, "email": email, "password": "secret1"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _pay(client, h, plan="pro", payment_id="pay_inv1"):
    order = client.post("/api/billing/order", headers=h, json={"plan": plan}).json()
    sig = hmac.new(SECRET.encode(), f"{order['orderId']}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    r = client.post("/api/billing/verify", headers=h,
                    json={"orderId": order["orderId"], "paymentId": payment_id, "signature": sig})
    assert r.status_code == 200
    return order


def test_every_payment_gets_the_next_invoice_number_and_a_pdf(client, sent):
    import invoices
    h = _user(client, "inv1@test.com")
    first = _pay(client, h, payment_id="pay_a")
    second = _pay(client, h, payment_id="pay_b")
    rows = client.get("/api/billing/payments", headers=h).json()["payments"]
    numbers = {r["orderId"]: r["invoiceNo"] for r in rows}
    fy = invoices.financial_year(invoices.datetime.now(invoices.limits.IST))
    a, b = numbers[first["orderId"]], numbers[second["orderId"]]
    assert a.startswith(f"KAI/{fy}/") and b.startswith(f"KAI/{fy}/")
    assert int(b.rsplit("/", 1)[1]) == int(a.rsplit("/", 1)[1]) + 1

    pdf = client.get(f"/api/billing/invoices/{first['orderId']}.pdf", headers=h)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF") and "inline" in pdf.headers["content-disposition"]
    dl = client.get(f"/api/billing/invoices/{first['orderId']}.pdf?download=1", headers=h)
    assert "attachment" in dl.headers["content-disposition"] and a.replace("/", "-") in dl.headers["content-disposition"]
    # The same number every time.
    again = client.get("/api/billing/payments", headers=h).json()["payments"]
    assert {r["orderId"]: r["invoiceNo"] for r in again} == numbers


def test_someone_elses_invoice_is_not_found(client, sent):
    h = _user(client, "inv2@test.com")
    order = _pay(client, h, payment_id="pay_c")
    other = _user(client, "inv3@test.com")
    assert client.get(f"/api/billing/invoices/{order['orderId']}.pdf", headers=other).status_code == 404
    assert client.get(f"/api/billing/invoices/{order['orderId']}.pdf").status_code == 401


def test_the_invoice_email_has_the_pdf_attached(client, sent):
    import invoices
    import server
    h = _user(client, "inv4@test.com", "Ravi Kumar")
    order = _pay(client, h, payment_id="pay_d")
    sent.clear()
    client.portal.call(invoices.issue, server.db, order["orderId"])  # what runs in the background after a payment
    mail = next(m for m in sent if m["attachments"])
    assert mail["to"] == "inv4@test.com" and "invoice" in mail["subject"].lower() and "₹499.00" in mail["subject"]
    name, content = mail["attachments"][0]
    assert name.startswith("Krish-AI-Invoice-KAI-") and base64.b64decode(content).startswith(b"%PDF")
    assert "Hi Ravi" in mail["html"]
    # Sent once.
    client.portal.call(invoices.issue, server.db, order["orderId"])
    assert len([m for m in sent if m["attachments"]]) == 1


def test_amounts_in_words_and_indian_digits():
    import invoices
    assert invoices.in_words(51200) == "Rupees Five Hundred Twelve Only"
    assert invoices.in_words(132131) == "Rupees One Thousand Three Hundred Twenty One and Thirty One Paise Only"
    assert invoices.rupees(12990000) == "₹1,29,900.00"
    assert invoices.rupees(49900) == "₹499.00"


def test_gst_split_and_offer_lines(monkeypatch):
    import invoices
    monkeypatch.setenv("GSTIN", "06ABCDE1234F1Z5")
    pay = {"plan": "pro", "amount": 39920 + 7186 + 1400, "baseAmount": 39920, "gst": 7186, "platformFee": 1400,
           "promoCode": "LAUNCH20"}
    amt = invoices.lines(pay)
    assert amt["listed"] == 49900 and amt["discount"] == 9980 and amt["cgst"] + amt["sgst"] == 7186
    assert amt["listed"] - amt["discount"] + amt["gst"] + amt["fee"] == amt["total"]
    pay.update(orderId="o", paymentId="pay_x", paidAt="2026-11-21T05:10:00+00:00", createdAt="2026-11-21T05:10:00+00:00",
               invoice={"number": "KAI/2026-27/0001", "date": "2026-11-21T05:10:00+00:00", "name": "A", "email": "a@b.c"})
    assert invoices.pdf(pay).startswith(b"%PDF")


def test_financial_year_turns_over_in_april_ist():
    from datetime import datetime
    import invoices
    assert invoices.financial_year(datetime.fromisoformat("2027-03-31T18:00:00+00:00")) == "2026-27"
    assert invoices.financial_year(datetime.fromisoformat("2027-03-31T19:00:00+00:00")) == "2027-28"  # 00:30 IST


def test_pages_on_the_onrender_address_move_to_krishai_net(client):
    r = client.get("/plans?x=1", headers={"host": "radha-u4he.onrender.com"}, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "https://krishai.net/plans?x=1"
    # The API (health checks, Razorpay's webhook) still answers there, and krishai.net itself isn't redirected.
    assert client.get("/api/", headers={"host": "radha-u4he.onrender.com"}).status_code == 200
    assert client.get("/plans", headers={"host": "krishai.net"}, follow_redirects=False).status_code != 301
