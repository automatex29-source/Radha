"""Invoices for Pro and Max payments: a numbered PDF for every successful payment, emailed to the customer
and kept in Settings > Billing to view or download again.

Each paid payment gets one invoice number, in order within the Indian financial year (April to March):
KAI/2026-27/0001, KAI/2026-27/0002, ... The number and the customer's name and email at the time are saved on
the payment, so the same invoice comes out every time it is downloaded. Payments made before invoices existed
get their number the first time the Billing page lists them.

With a GSTIN set (see billing.gstin) the PDF is a Tax Invoice with the 18% GST split into CGST 9% and SGST 9%
(an online sale to a person whose state isn't known is taxed where the seller is). Without one it is a plain
invoice that says GST wasn't charged.

Optional settings (Render > Environment), printed on every invoice:
  BUSINESS_NAME      the legal name of the seller (default EmpireX)
  BUSINESS_ADDRESS   the registered address, on one line
  INVOICE_PREFIX     the start of every invoice number (default KAI)
  INVOICE_SAC        the GST service code for the plans (default 998314, IT services)
"""
import asyncio
import base64
import html as _html
import logging
import os
from datetime import datetime
from pathlib import Path

from pymongo import ReturnDocument

import limits

logger = logging.getLogger("radha.invoices")

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO = ASSETS / "krish-icon-512.png"
FONTS = ASSETS / "fonts" / "noto"
HELP_EMAIL = "empirex.support@gmail.com"
_TASKS: set = set()

INK = (21, 26, 40)
MUTED = (110, 117, 135)
LINE = (226, 229, 236)
BRAND = (255, 138, 30)
SOFT = (247, 248, 251)


def seller() -> dict:
    import billing
    return {
        "name": os.environ.get("BUSINESS_NAME", "").strip() or "EmpireX",
        "address": os.environ.get("BUSINESS_ADDRESS", "").strip(),
        "gstin": billing.gstin(),
        "email": (os.environ.get("SUPPORT_EMAIL") or HELP_EMAIL).strip(),
        "website": "krishai.net",
    }


def _prefix() -> str:
    return (os.environ.get("INVOICE_PREFIX", "").strip() or "KAI").upper()


def _sac() -> str:
    return os.environ.get("INVOICE_SAC", "").strip() or "998314"


def financial_year(when: datetime) -> str:
    """The Indian financial year of `when` (in IST), e.g. '2026-27' for 21 Nov 2026."""
    d = when.astimezone(limits.IST)
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def _paid_at(pay: dict) -> datetime:
    return datetime.fromisoformat(pay.get("paidAt") or pay["createdAt"])


async def assign(db, pay: dict) -> dict:
    """Give a paid payment its invoice (number, date, who it's billed to), once. Returns the invoice."""
    if pay.get("invoice"):
        return pay["invoice"]
    user = await db.users.find_one({"id": pay["userId"]}, {"name": 1, "email": 1}) or {}
    fy = financial_year(_paid_at(pay))
    counter = await db.counters.find_one_and_update(
        {"_id": f"invoice:{fy}"}, {"$inc": {"n": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
    invoice = {"number": f"{_prefix()}/{fy}/{counter['n']:04d}", "date": pay.get("paidAt") or pay["createdAt"],
               "name": (user.get("name") or "").strip(), "email": (user.get("email") or "").strip()}
    res = await db.payments.update_one({"orderId": pay["orderId"], "invoice": {"$exists": False}},
                                       {"$set": {"invoice": invoice}})
    if not res.modified_count:  # another request numbered it first
        again = await db.payments.find_one({"orderId": pay["orderId"]}, {"invoice": 1})
        return (again or {}).get("invoice") or invoice
    return invoice


async def backfill(db, user_id: str) -> None:
    """Number the user's paid payments that have no invoice yet, oldest first."""
    rows = await db.payments.find({"userId": user_id, "status": {"$in": ["paid", "captured"]},
                                   "invoice": {"$exists": False}}).sort("createdAt", 1).to_list(200)
    for pay in rows:
        await assign(db, pay)


# ------------------------------------------------------------------ amounts
def lines(pay: dict) -> dict:
    """What the invoice shows, in paise: the plan at its list price, any offer, GST and the platform fee."""
    plan = limits.PLANS.get(pay.get("plan"), {})
    total = int(pay.get("amount") or 0)
    gst = int(pay.get("gst") or 0)
    fee = int(pay.get("platformFee") or 0)
    taxable = int(pay.get("baseAmount") or (total - gst - fee))
    listed = int((plan.get("price") or 0) * 100)
    discount = listed - taxable if pay.get("promoCode") and listed > taxable else 0
    return {"planName": plan.get("name") or str(pay.get("plan", "")).title(), "listed": taxable + discount,
            "discount": discount, "taxable": taxable, "gst": gst, "cgst": gst // 2, "sgst": gst - gst // 2,
            "fee": fee, "total": total}


def rupees(paise: int) -> str:
    """Rs 1,29,900.00 written the Indian way (lakhs), with the rupee sign."""
    neg = paise < 0
    whole, frac = divmod(abs(int(paise)), 100)
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        s = ",".join(([head] if head else []) + parts + [tail])
    return f"{'-' if neg else ''}₹{s}.{frac:02d}"


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
         "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return (_TENS[n // 10] + " " + _ONES[n % 10]).strip()
    if n < 1000:
        return (_ONES[n // 100] + " Hundred " + _words(n % 100)).strip()
    for size, name in ((10**7, "Crore"), (10**5, "Lakh"), (1000, "Thousand")):
        if n >= size:
            return (_words(n // size) + f" {name} " + _words(n % size)).strip()
    return ""


def in_words(paise: int) -> str:
    """'Rupees Five Hundred Twelve Only' (with paise when there are any)."""
    whole, frac = divmod(int(paise), 100)
    text = "Rupees " + (_words(whole) or "Zero")
    if frac:
        text += " and " + _words(frac) + " Paise"
    return text + " Only"


def _date(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(limits.IST).strftime("%d %b %Y")


# ------------------------------------------------------------------ PDF
def pdf(pay: dict) -> bytes:
    """The invoice as an A4 PDF."""
    from fpdf import FPDF

    inv = pay["invoice"]
    me = seller()
    amt = lines(pay)
    taxed = amt["gst"] > 0
    doc = FPDF(format="A4", unit="mm")
    doc.set_auto_page_break(False)
    doc.set_margins(18, 18, 18)
    doc.add_font("Noto", "", str(FONTS / "NotoSans-Regular.ttf"))
    doc.add_font("Noto", "B", str(FONTS / "NotoSans-Bold.ttf"))
    doc.set_title(f"Invoice {inv['number']}")
    doc.set_author(me["name"])
    doc.set_creator("Krish AI")
    doc.add_page()
    W = doc.w - 36  # width inside the margins
    L = 18

    def text(x, y, s, size=9.5, bold=False, color=INK, w=0, align="L"):
        doc.set_font("Noto", "B" if bold else "", size)
        doc.set_text_color(*color)
        doc.set_xy(x, y)
        doc.cell(w or doc.get_string_width(s) + 1, size * 0.45, s, align=align)

    # Brand band
    doc.set_fill_color(*BRAND)
    doc.rect(0, 0, doc.w, 3, "F")

    # Seller, with the logo
    if LOGO.exists():
        doc.image(str(LOGO), x=L - 2, y=14, w=20, h=20)
    text(L + 20, 17, "Krish AI", 17, True)
    text(L + 20, 25.5, f"by {me['name']}", 9.5, color=MUTED)
    y = 38
    if me["address"]:
        doc.set_font("Noto", "", 8.8)
        doc.set_text_color(*MUTED)
        doc.set_xy(L, y)
        doc.multi_cell(80, 4.4, me["address"])
        y = doc.get_y()
    if me["gstin"]:
        text(L, y, f"GSTIN: {me['gstin']}", 8.8, True)
        y += 4.4
    text(L, y, f"{me['email']}  ·  {me['website']}", 8.8, color=MUTED)
    seller_end = y + 4.4

    # Title and invoice details, on the right
    title = "TAX INVOICE" if taxed else "INVOICE"
    text(L, 16, title, 20, True, w=W, align="R")
    rows = [("Invoice no.", inv["number"]), ("Invoice date", _date(inv["date"])),
            ("Payment ID", pay.get("paymentId") or "-")]
    y = 27
    for label, value in rows:
        text(L, y, label, 8.5, color=MUTED, w=W - 52, align="R")
        text(L, y, value, 8.8, True, w=W, align="R")
        y += 4.6
    # PAID stamp
    doc.set_draw_color(22, 163, 74)
    doc.set_text_color(22, 163, 74)
    doc.set_line_width(0.5)
    doc.set_font("Noto", "B", 9)
    doc.set_xy(L + W - 22, y + 1.5)
    doc.cell(22, 7, "PAID", border=1, align="C")

    # Billed to
    y = max(seller_end, y + 10) + 6
    doc.set_draw_color(*LINE)
    doc.set_line_width(0.3)
    doc.line(L, y, L + W, y)
    y += 6
    text(L, y, "BILLED TO", 8, True, MUTED)
    text(L + W / 2, y, "PAID WITH", 8, True, MUTED)
    y += 5
    text(L, y, inv.get("name") or "Krish AI customer", 10.5, True)
    text(L + W / 2, y, "Razorpay" + (" · Autopay" if pay.get("autopay") else ""), 10.5, True)
    y += 5.2
    if inv.get("email"):
        text(L, y, inv["email"], 9, color=MUTED)
    text(L + W / 2, y, f"Paid on {_date(pay.get('paidAt') or pay['createdAt'])}", 9, color=MUTED)
    y += 12

    # Items
    cols = [("#", 8, "L"), ("Description", W - 8 - 22 - 12 - 32, "L"), ("SAC", 22, "L"), ("Qty", 12, "R"),
            ("Amount", 32, "R")]
    doc.set_fill_color(*SOFT)
    doc.rect(L, y, W, 8, "F")
    x = L
    for name, w, align in cols:
        text(x + (2 if align == "L" else 0), y + 2, name, 8.5, True, MUTED, w=w - 2, align=align)
        x += w
    y += 8
    start_dt = datetime.fromisoformat(pay.get("paidAt") or pay["createdAt"])
    items = [(f"Krish AI {amt['planName']} plan, 30 days",
              f"{'Monthly autopay' if pay.get('autopay') else 'One-time payment'} · from {_date(start_dt.isoformat())}",
              _sac(), amt["listed"])]
    if amt["discount"]:
        items.append((f"Offer {pay.get('promoCode')}", "Discount on the plan", "", -amt["discount"]))
    for i, (desc, sub, sac, value) in enumerate(items, 1):
        x = L
        text(x + 2, y + 3, str(i), 9.5, w=cols[0][1] - 2)
        x += cols[0][1]
        text(x + 2, y + 3, desc, 9.8, True, w=cols[1][1] - 2)
        text(x + 2, y + 8, sub, 8.3, color=MUTED, w=cols[1][1] - 2)
        x += cols[1][1]
        text(x + 2, y + 3, sac, 9, w=cols[2][1] - 2)
        x += cols[2][1]
        text(x, y + 3, "1" if value > 0 else "", 9, w=cols[3][1], align="R")
        x += cols[3][1]
        text(x, y + 3, rupees(value), 9.8, True, w=cols[4][1], align="R")
        y += 14
        doc.line(L, y, L + W, y)

    # Totals
    y += 5
    tx, tw = L + W - 82, 82
    totals = [("Taxable value" if taxed else "Subtotal", amt["taxable"])]
    if taxed:
        totals += [("CGST @ 9%", amt["cgst"]), ("SGST @ 9%", amt["sgst"])]
    if amt["fee"]:
        totals.append(("Platform fee (payment processing)", amt["fee"]))
    for label, value in totals:
        text(tx, y, label, 9, color=MUTED, w=tw - 34)
        text(tx, y, rupees(value), 9.5, w=tw, align="R")
        y += 6
    y += 1
    doc.set_fill_color(*INK)
    doc.rect(tx - 3, y - 1.5, tw + 3, 11, "F")
    text(tx, y + 1.3, "Total paid", 10.5, True, (255, 255, 255), w=tw - 34)
    text(tx, y + 1.3, rupees(amt["total"]), 11.5, True, (255, 255, 255), w=tw - 1, align="R")
    y += 15
    text(L, y, "Amount in words", 8, True, MUTED)
    text(L, y + 4.5, in_words(amt["total"]), 9.3, True, w=W)
    y += 14
    note = ("GST at 18% is charged on the plan's taxable value, as shown above." if taxed else
            "GST not charged: the seller is not registered under GST.")
    text(L, y, note, 8.5, color=MUTED, w=W)
    if amt["fee"]:
        text(L, y + 4.4, "The platform fee covers the payment gateway's charges.", 8.5, color=MUTED, w=W)

    # Footer
    fy = doc.h - 30
    doc.line(L, fy, L + W, fy)
    text(L, fy + 4, "Thank you for choosing Krish AI.", 10, True)
    text(L, fy + 9.5, "This is a computer-generated invoice and does not need a signature.", 8.3, color=MUTED, w=W)
    text(L, fy + 14, f"Questions about this invoice? Write to {me['email']}", 8.3, color=MUTED, w=W)
    return bytes(doc.output())


def filename(pay: dict) -> str:
    return f"Krish-AI-Invoice-{pay['invoice']['number'].replace('/', '-')}.pdf"


# ------------------------------------------------------------------ email
def email(app_url: str, pay: dict) -> tuple:
    """(subject, html, text) for the "payment received, here's your invoice" email."""
    inv = pay["invoice"]
    amt = lines(pay)
    me = seller()
    first = (inv.get("name") or "").split(" ")[0][:30]
    total = rupees(amt["total"])
    subject = f"Your Krish AI invoice {inv['number']} · {total} paid"
    logo = f"{app_url}/icon-192.png" if app_url else ""
    billing = f"{app_url}/?settings=billing" if app_url else ""
    rows = [("Plan", f"Krish AI {amt['planName']}, 30 days"), ("Invoice no.", inv["number"]),
            ("Date", _date(inv["date"])), ("Payment ID", pay.get("paymentId") or "-")]
    if amt["discount"]:
        rows.append((f"Offer {pay.get('promoCode')}", f"-{rupees(amt['discount'])}"))
    if amt["gst"]:
        rows.append(("GST (18%)", rupees(amt["gst"])))
    if amt["fee"]:
        rows.append(("Platform fee", rupees(amt["fee"])))
    esc = _html.escape
    table = "".join(
        f'<tr><td style="padding:9px 0;color:#6e7587;font-size:14px;border-bottom:1px solid #eef0f4">{esc(k)}</td>'
        f'<td align="right" style="padding:9px 0;font-size:14px;font-weight:600;border-bottom:1px solid #eef0f4">{esc(v)}</td></tr>'
        for k, v in rows)
    hello = f"Hi {esc(first)}," if first else "Hi,"
    body = f"""<!doctype html><html><body style="margin:0;background:#f4f5f9;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#151a28">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:18px;overflow:hidden">
<tr><td style="height:4px;background:#ff8a1e;font-size:0;line-height:0">&nbsp;</td></tr>
<tr><td style="padding:26px 28px 6px">
<table role="presentation" cellpadding="0" cellspacing="0"><tr>
{f'<td style="padding-right:10px"><img src="{logo}" width="40" height="40" alt="Krish AI" style="display:block;border:0"></td>' if logo else ""}
<td style="font-size:18px;font-weight:800;letter-spacing:-0.3px">Krish AI<br><span style="font-size:12px;font-weight:500;color:#8a90a2">by {esc(me['name'])}</span></td>
</tr></table></td></tr>
<tr><td style="padding:18px 28px 4px">
<p style="margin:0 0 6px;font-size:12px;font-weight:700;letter-spacing:1.2px;color:#16a34a">PAYMENT RECEIVED</p>
<p style="margin:0;font-size:34px;font-weight:800;letter-spacing:-1px">{esc(total)}</p>
<p style="margin:14px 0 18px;font-size:15px;line-height:1.6;color:#2a3042">{hello} thank you for your payment. Your invoice is attached
as a PDF, and you can view or download it any time in <b>Settings &gt; Billing</b>.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{table}
<tr><td style="padding:12px 0 0;font-size:15px;font-weight:800">Total paid</td>
<td align="right" style="padding:12px 0 0;font-size:15px;font-weight:800">{esc(total)}</td></tr></table>
{f'<p style="margin:24px 0 8px"><a href="{billing}" style="display:inline-block;background:#151a28;color:#ffffff;text-decoration:none;font-weight:700;font-size:15px;padding:13px 26px;border-radius:12px">View invoices</a></p>' if billing else ""}
</td></tr>
<tr><td style="padding:18px 28px 26px"><p style="margin:0;font-size:12.5px;line-height:1.6;color:#8a90a2">
Questions about this payment? Write to <a href="mailto:{esc(me['email'])}" style="color:#6e7587">{esc(me['email'])}</a>.
{"GSTIN " + esc(me['gstin']) + ". " if me['gstin'] else ""}{esc(me['name'])}{", " + esc(me['address']) if me['address'] else ""}.</p></td></tr>
</table>
<p style="font-size:12px;color:#8a90a2;margin-top:16px">Krish AI by {esc(me['name'])} · krishai.net</p>
</td></tr></table></body></html>"""
    text = "\n".join([f"{hello} thank you for your payment of {total} to Krish AI.", ""]
                     + [f"{k}: {v}" for k, v in rows] + [f"Total paid: {total}", "",
                     "Your invoice is attached as a PDF. You can also view it in Settings > Billing"
                     + (f": {billing}" if billing else "."), "", f"Questions? Write to {me['email']}",
                     f"Krish AI by {me['name']}"])
    return subject, body, text


async def issue(db, order_id: str) -> None:
    """After a payment: number its invoice and email it with the PDF attached. Never raises."""
    try:
        import growth_mail
        import mailer
        pay = await db.payments.find_one({"orderId": order_id})
        if not pay or pay.get("status") not in ("paid", "captured"):
            return
        pay["invoice"] = await assign(db, pay)
        to = pay["invoice"].get("email")
        if not to or not mailer.configured() or pay.get("invoiceEmailedAt"):
            return
        subject, body, text = email(growth_mail.app_url(), pay)
        await mailer.send(to, subject, body, text,
                          attachments=[(filename(pay), base64.b64encode(pdf(pay)).decode())])
        await db.payments.update_one({"orderId": order_id}, {"$set": {"invoiceEmailedAt": datetime.now().isoformat()}})
    except Exception as exc:  # an invoice email must never break a payment
        logger.warning("Invoice for order %s failed: %s", order_id, exc)


def issue_later(db, order_id: str) -> None:
    task = asyncio.create_task(issue(db, order_id))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
