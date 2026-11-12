"""Ready-made Indian documents: the everyday papers people in India need, in the format offices expect.

Each one is a short form (a few boxes) plus a free "say it your way" box that takes typed or spoken Hinglish.
Krish turns that into a finished document in Docs, which downloads as Word or PDF.

- The GST invoice is worked out here with no AI at all, so the tax sums are always right (CGST + SGST inside
  one state, IGST across states) and it costs nothing.
- Every other document is one AI call with a format guide written for India, on the cheap default model.
"""
import re
from typing import Dict, List, Optional

# Each field: (key, label, placeholder). Every field is optional: what's missing is left as a blank to fill.
DOCS: List[dict] = [
    {"id": "gst_invoice", "title": "GST tax invoice", "hindi": "GST बिल", "icon": "receipt", "ai": False,
     "hint": "A proper tax invoice with CGST, SGST or IGST worked out for you.",
     "fields": [("seller", "Your business name and address", "Sharma Traders, MG Road, Pune"),
                ("seller_gstin", "Your GSTIN", "27ABCDE1234F1Z5"),
                ("buyer", "Customer name and address", "Mehta Stores, Andheri, Mumbai"),
                ("buyer_gstin", "Customer GSTIN (if any)", ""),
                ("items", "Items, one per line: name, quantity, rate", "Rice 25kg bag, 4, 1450\nSugar 1kg, 20, 46"),
                ("gst_rate", "GST rate %", "5"),
                ("interstate", "Customer in another state? (yes / no)", "no"),
                ("invoice_no", "Invoice number", "INV-0042")]},
    {"id": "rent_agreement", "title": "Rent agreement", "hindi": "किराया अनुबंध", "icon": "home", "ai": True,
     "hint": "An 11-month leave and licence agreement, ready to print on stamp paper.",
     "fields": [("owner", "Owner's name and address", ""), ("tenant", "Tenant's name and address", ""),
                ("property", "Flat or house address", "2BHK, Flat 304, Sunrise Apartments, Baner, Pune"),
                ("rent", "Monthly rent (₹)", "18000"), ("deposit", "Security deposit (₹)", "50000"),
                ("start", "Start date", "1 December 2026")],
     "guide": "An Indian 11-month leave and licence (rent) agreement. Sections: parties, property, term of 11 months, "
              "monthly rent and due date, security deposit and its refund, maintenance and electricity bills, use only "
              "for residence, no subletting, notice period of one month, lock-in if any, repairs, inspection, "
              "termination, witnesses (two blank lines), signatures. Note at top: to be printed on stamp paper "
              "of the value required in the state."},
    {"id": "leave_application", "title": "Leave application", "hindi": "छुट्टी की अर्ज़ी", "icon": "calendar", "ai": True,
     "hint": "For your office, school or college.",
     "fields": [("name", "Your name", ""), ("to", "To (manager, principal…)", "The Principal, DPS Noida"),
                ("days", "Which days", "13 to 15 November"), ("reason", "Reason", "my sister's wedding")],
     "guide": "A polite Indian leave application letter: To, date, subject line, Respected Sir/Madam, the request with "
              "dates and reason, promise to finish pending work or cover studies, thanking you, yours "
              "sincerely/obediently, name."},
    {"id": "biodata", "title": "Marriage biodata", "hindi": "शादी का बायोडाटा", "icon": "heart", "ai": True,
     "hint": "A neat, respectful biodata with family details.",
     "fields": [("name", "Name", ""), ("birth", "Date, time and place of birth", ""),
                ("height", "Height", "5 ft 6 in"), ("education", "Education and job", ""),
                ("family", "Father, mother, brothers and sisters", ""),
                ("other", "Religion, caste, gotra, rashi, hobbies (any you want)", "")],
     "guide": "An Indian marriage biodata. Start with a small auspicious line (|| Shri Ganeshay Namah || or a fitting "
              "one for the religion given, else none). Sections as short label: value lines: Personal details, "
              "Education and career, Family details, Contact (blank lines). Warm, respectful, no exaggeration."},
    {"id": "rti", "title": "RTI application", "hindi": "RTI आवेदन", "icon": "landmark", "ai": True,
     "hint": "Ask any government office for information under the RTI Act, 2005.",
     "fields": [("name", "Your name and address", ""), ("office", "Government office or department", ""),
                ("info", "What information you want", ""), ("bpl", "Below poverty line? (yes / no)", "no")],
     "guide": "An application under Section 6(1) of the Right to Information Act, 2005, to the Public Information "
              "Officer of the office named. Include: subject, applicant details, the information sought as a numbered "
              "list of clear questions, period it covers, fee of ₹10 paid by (blank: IPO / DD / court fee stamp) or "
              "BPL exemption with proof if BPL, request for reply within 30 days, place, date, signature."},
    {"id": "resume", "title": "Resume", "hindi": "रिज़्यूमे", "icon": "user", "ai": True,
     "hint": "A clean one-page resume for Indian jobs and campus placements.",
     "fields": [("name", "Name, phone, email, city", ""), ("role", "Job you want", ""),
                ("education", "Education (with marks or CGPA)", ""), ("work", "Work, internships or projects", ""),
                ("skills", "Skills and languages", "")],
     "guide": "A one-page resume for Indian employers: name and contact line, a 2-line career objective for the role, "
              "Education (latest first, with % or CGPA), Experience or Projects with strong action-verb bullets and "
              "numbers where given, Skills, Languages known, and a short Declaration line with place and date. Don't "
              "invent jobs, marks or numbers that weren't given."},
    {"id": "affidavit", "title": "Affidavit", "hindi": "शपथ पत्र", "icon": "scale", "ai": True,
     "hint": "General, name change, address proof, income or gap year.",
     "fields": [("name", "Your name, father's or husband's name, age, address", ""),
                ("purpose", "What it is for", "name change from Pooja Sharma to Pooja Verma after marriage")],
     "guide": "An Indian general affidavit: title AFFIDAVIT, 'I, ___, son/daughter/wife of ___, aged ___, residing at "
              "___, do hereby solemnly affirm and declare as under:', numbered statements for the purpose, a "
              "statement that the contents are true to my knowledge and nothing is concealed, DEPONENT signature "
              "line, VERIFICATION paragraph with place and date. Note at top: print on stamp paper and get it "
              "notarised."},
    {"id": "police_complaint", "title": "Police complaint", "hindi": "पुलिस शिकायत", "icon": "shield", "ai": True,
     "hint": "For a lost phone or documents, theft, or cyber fraud.",
     "fields": [("name", "Your name, address and phone", ""), ("station", "Police station", ""),
                ("what", "What happened, when and where", "my phone was stolen in a bus on 10 Nov, 6 pm, near Sector 18")],
     "guide": "A written complaint to the Station House Officer (SHO) of the police station named: To, date, subject, "
              "Respected Sir/Madam, the facts in order (what, when, where, who if known, items with details like "
              "IMEI/serial if given), request to register an FIR or record it and to give a copy/acknowledgement. "
              "For cyber fraud also tell them to call 1930 and report at cybercrime.gov.in. Yours faithfully, name."},
    {"id": "bank_letter", "title": "Letter to the bank", "hindi": "बैंक को पत्र", "icon": "landmark", "ai": True,
     "hint": "Address change, account closure, stop cheque, new cheque book…",
     "fields": [("name", "Your name and account number", ""), ("bank", "Bank and branch", "SBI, Kothrud branch, Pune"),
                ("request", "What you need", "change my address to …")],
     "guide": "A formal letter to the Branch Manager of the bank and branch named: To, date, subject with account "
              "number, Respected Sir/Madam, the request clearly, documents enclosed (if any apply, as a short list), "
              "thanking you, yours faithfully, name, signature, phone."},
    {"id": "fee_receipt", "title": "Fee or rent receipt", "hindi": "रसीद", "icon": "receipt", "ai": True,
     "hint": "A simple signed receipt for rent, tuition or any payment.",
     "fields": [("from", "Received from", ""), ("by", "Received by (your name)", ""), ("amount", "Amount (₹)", ""),
                ("for", "For what and which month", "rent for November 2026, Flat 304"),
                ("mode", "Paid by (cash, UPI, cheque…)", "UPI")],
     "guide": "A short payment receipt: title RECEIPT, receipt number blank, date, 'Received with thanks from ___ the "
              "sum of ₹___ (Rupees ___ only) towards ___ by ___.', and a signature line for the receiver. For rent "
              "receipts add a note that a revenue stamp is needed for cash payments over ₹5,000."},
]
BY_ID: Dict[str, dict] = {d["id"]: d for d in DOCS}

SYSTEM = (
    "You write ready-to-use Indian documents in Markdown for Krish AI Docs. Use the format given exactly. Write in "
    "the language the details are in when it is Hindi in Devanagari; for English or Hinglish details write proper "
    "English. Use the details given. Where something needed isn't given, leave a blank like ________ for the person "
    "to fill in. Never make up names, numbers, dates or legal claims. Start with a # title. Reply with ONLY the "
    "document: no preamble, no notes about what you did, no code fences."
)


def public_list() -> List[dict]:
    return [{"id": d["id"], "title": d["title"], "hindi": d["hindi"], "icon": d["icon"], "hint": d["hint"],
             "fields": [{"key": k, "label": label, "placeholder": ph} for k, label, ph in d["fields"]]}
            for d in DOCS]


def _clean(values: Optional[dict], d: dict) -> dict:
    keys = {k for k, _, _ in d["fields"]}
    return {k: str(v).strip()[:2000] for k, v in (values or {}).items() if k in keys and str(v or "").strip()}


def prompt_for(doc_id: str, values: Optional[dict], said: str = "") -> str:
    d = BY_ID[doc_id]
    vals = _clean(values, d)
    lines = [f"- {label}: {vals[k]}" for k, label, _ in d["fields"] if k in vals]
    said = (said or "").strip()[:3000]
    return (f"Write: {d['title']}.\nFormat: {d['guide']}\n\nDetails given:\n" + ("\n".join(lines) or "- (none)")
            + (f"\n\nIn the person's own words (may be Hinglish or spoken): {said}" if said else ""))


# ---------------------------------------------------------------------------------------------- GST invoice
_NUM = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def _num(text: str) -> Optional[float]:
    m = _NUM.search(text or "")
    return float(m.group(0).replace(",", "")) if m else None


def _rupees(x: float) -> str:
    """Indian grouping: 1,23,456.50"""
    neg, x = x < 0, abs(round(x, 2))
    whole, frac = f"{x:.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    if head:
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1]) + ","
    return f"{'-' if neg else ''}₹{head}{tail}.{frac}"


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
         "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _below_100(n: int) -> str:
    return _ONES[n] if n < 20 else (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else ""))


def _below_1000(n: int) -> str:
    head = f"{_ONES[n // 100]} Hundred" if n >= 100 else ""
    return " ".join(x for x in (head, _below_100(n % 100)) if x)


def in_words(x: float) -> str:
    """7318.50 -> 'Rupees Seven Thousand Three Hundred Eighteen and Fifty Paise Only' (lakh and crore)."""
    rupees, paise = int(x), round((x - int(x)) * 100)
    parts, n = [], rupees
    for size, name in ((10 ** 7, "Crore"), (10 ** 5, "Lakh"), (1000, "Thousand")):
        if n >= size:
            parts.append(f"{_below_1000(n // size) if n // size < 1000 else in_words(n // size)[7:-5]} {name}")
            n %= size
    if n:
        parts.append(_below_1000(n))
    words = " ".join(parts) or "Zero"
    return f"Rupees {words}" + (f" and {_below_100(paise)} Paise" if paise else "") + " Only"


def parse_items(text: str) -> List[dict]:
    """'Rice 25kg bag, 4, 1450' per line -> name, qty, rate. A line with only one number is a single item at that
    price; a line with no number is skipped."""
    out = []
    for line in (text or "").splitlines():
        parts = [p.strip() for p in re.split(r"[,|\t;]", line) if p.strip()]
        if not parts:
            continue
        nums = [_num(p) for p in parts[1:] if _NUM.fullmatch(p.replace("₹", "").replace("Rs", "").strip())]
        name = parts[0]
        if len(nums) >= 2:
            qty, rate = nums[0], nums[1]
        elif len(nums) == 1:
            qty, rate = 1, nums[0]
        else:
            continue
        out.append({"name": name, "qty": qty, "rate": rate, "amount": round(qty * rate, 2)})
    return out


def gst_invoice(values: Optional[dict], today: str) -> str:
    v = _clean(values, BY_ID["gst_invoice"])
    rate = _num(v.get("gst_rate", "")) if v.get("gst_rate") else 18.0
    rate = rate if rate is not None and 0 <= rate <= 40 else 18.0
    inter = (v.get("interstate", "").lower()[:1] in ("y", "h"))  # yes / haan
    items = parse_items(v.get("items", ""))
    blank = "________"
    rows = [f"| {i} | {it['name']} | {it['qty']:g} | {_rupees(it['rate'])} | {_rupees(it['amount'])} |"
            for i, it in enumerate(items, 1)] or [f"| 1 | {blank} | | | |"]
    taxable = round(sum(it["amount"] for it in items), 2)
    tax = round(taxable * rate / 100, 2)
    total = round(taxable + tax, 2)
    if inter:
        tax_rows = [f"| IGST @ {rate:g}% | {_rupees(tax)} |"]
    else:
        half = round(tax / 2, 2)
        tax_rows = [f"| CGST @ {rate / 2:g}% | {_rupees(half)} |", f"| SGST @ {rate / 2:g}% | {_rupees(tax - half)} |"]
    return "\n".join([
        "# Tax Invoice", "",
        f"**Invoice no.:** {v.get('invoice_no', blank)}  ", f"**Date:** {today}", "",
        f"**From:** {v.get('seller', blank)}  ", f"**GSTIN:** {v.get('seller_gstin', blank)}", "",
        f"**Bill to:** {v.get('buyer', blank)}  ", f"**GSTIN:** {v.get('buyer_gstin', 'Unregistered')}  ",
        f"**Supply:** {'Inter-state (IGST)' if inter else 'Within the state (CGST + SGST)'}", "",
        "| # | Item | Qty | Rate | Amount |", "|---|---|---:|---:|---:|", *rows, "",
        "| Summary | Amount |", "|---|---:|", f"| Taxable value | {_rupees(taxable)} |", *tax_rows,
        f"| **Total** | **{_rupees(total)}** |", "", f"**Amount in words:** {in_words(total)}", "",
        "Add HSN/SAC codes against each item if your turnover needs them.", "",
        "For " + (v.get("seller", "").split(",")[0] or blank), "", "", "Authorised signatory",
    ])
