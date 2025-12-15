import os, io, re, shutil, tempfile, secrets, base64, hashlib, datetime, json, subprocess
from flask import Flask, render_template, render_template_string, request, session, redirect, url_for, send_file
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
# PDF compose
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader
from PyPDF2 import PdfReader, PdfWriter
# Notion + data
import requests
import pandas as pd
import numpy as np
# HTML→PDF (Playwright)
from playwright.sync_api import sync_playwright

# -------------------------------------------------------------------
# Load env + Flask
# -------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(16)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
app.config["PROPAGATE_EXCEPTIONS"] = True

# -------------------------------------------------------------------
# Notion basics
# -------------------------------------------------------------------
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

def notion_headers(json=True):
    if not NOTION_TOKEN:
        raise RuntimeError("NOTION_TOKEN not set in environment.")
    h = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
    }
    if json:
        h["Content-Type"] = "application/json"
    return h

# -------------------------------------------------------------------
# Your Notion DBs (pages)
# -------------------------------------------------------------------
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")  # Page 1 DB id (Borrower)
NOTION_DATABASE_ID_PAGE2 = os.getenv("NOTION_DATABASE_ID_PAGE2") or NOTION_DATABASE_ID
NOTION_DATABASE_ID_PAGE3 = os.getenv("NOTION_DATABASE_ID_PAGE3") or NOTION_DATABASE_ID_PAGE2
NOTION_DATABASE_ID_PAGE4 = os.getenv("NOTION_DATABASE_ID_PAGE4") or NOTION_DATABASE_ID_PAGE3  # Loan Application
NOTION_DATABASE_ID_PAGE5 = os.getenv("NOTION_DATABASE_ID_PAGE5") or NOTION_DATABASE_ID_PAGE4

# -------------------------------------------------------------------
# Paths / Constants
# -------------------------------------------------------------------
ROOT_DIR     = os.path.abspath(os.path.dirname(__file__))
TEMPLATE_DIR = ROOT_DIR
STATIC_DIR   = os.path.join(ROOT_DIR, "static")
CONTRACTS_DIR= os.path.join(ROOT_DIR, "contracts")

# KFS
KFS_TEMPLATE_FILENAME = os.getenv("KFS_TEMPLATE", "template.html")
KFS_FILES_PROP_NAME   = os.getenv("KFS_FILES_PROP_NAME", "Key Fact Sheet")
KFS_SIG_PAGE_INDEX = int(os.getenv("KFS_SIG_PAGE_INDEX", "1"))  # default to page 2
KFS_SIG_X_PT       = float(os.getenv("KFS_SIG_X_PT", "0"))
KFS_SIG_Y_PT       = float(os.getenv("KFS_SIG_Y_PT", "400"))
KFS_SIG_WIDTH_PT   = float(os.getenv("KFS_SIG_WIDTH_PT", "220"))

# Contract (use underscore filename consistently)
CONTRACT_TEMPLATE_FILENAME = "Microfinancing_Loan_Agreement.html"
CONTRACT_TEMPLATE_PATH = os.path.join(CONTRACTS_DIR, CONTRACT_TEMPLATE_FILENAME)
CONTRACT_FILES_PROP_NAME = os.getenv("CONTRACT_FILES_PROP_NAME", "Executed Contract")

CONTRACT_SIG_PAGE_INDEX = int(os.getenv("CONTRACT_SIG_PAGE_INDEX", "0"))
CONTRACT_SIG_X_PT       = float(os.getenv("CONTRACT_SIG_X_PT", "420"))
CONTRACT_SIG_Y_PT       = float(os.getenv("CONTRACT_SIG_Y_PT", "100"))
CONTRACT_SIG_WIDTH_PT   = float(os.getenv("CONTRACT_SIG_WIDTH_PT", "220"))

# Ledger DBs
NOTION_DB_DISBURSEMENTS = os.getenv("NOTION_DB_DISBURSEMENTS")
NOTION_DB_COLLECTIONS   = os.getenv("NOTION_DB_COLLECTIONS")
PROP_DISB_DATE   = os.getenv("PROP_DISB_DATE",   "Date")
PROP_DISB_AMOUNT = os.getenv("PROP_DISB_AMOUNT", "Amount")
PROP_COLL_DATE   = os.getenv("PROP_COLL_DATE",   "Date")
PROP_COLL_AMOUNT = os.getenv("PROP_COLL_AMOUNT", "Amount")
STARTING_CORPUS  = float(os.getenv("STARTING_CORPUS", "7500000"))

# -------------------------------------------------------------------
# Notion helpers
# -------------------------------------------------------------------
def query_notion_db(db_id: str, filter_block=None, sorts=None, page_size=100):
    payload = {"page_size": page_size}
    if filter_block:
        payload["filter"] = filter_block
    if sorts:
        payload["sorts"] = sorts
    results, cursor = [], None
    while True:
        if cursor:
            payload["start_cursor"] = cursor
        r = requests.post(f"{NOTION_API}/databases/{db_id}/query",
                          headers=notion_headers(), json=payload, timeout=90)
        if r.status_code >= 300:
            raise RuntimeError(f"Notion query failed: {r.status_code} {r.text}")
        data = r.json()
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return results

def parse_field(prop: dict):
    if not isinstance(prop, dict): return ""
    if "title" in prop:     return prop["title"][0]["plain_text"] if prop["title"] else ""
    if "rich_text" in prop: return prop["rich_text"][0]["plain_text"] if prop["rich_text"] else ""
    if "select" in prop and prop["select"]: return prop["select"]["name"]
    if "date" in prop and prop["date"]:     return prop["date"]["start"]
    if "number" in prop:    return "" if prop["number"] is None else str(prop["number"])
    if "formula" in prop:
        f = prop["formula"]
        if f["type"] == "string": return f["string"] or ""
        if f["type"] == "number": return "" if f["number"] is None else str(f["number"])
        if f["type"] == "date":   return f["date"]["start"] if f["date"] else ""
    if "rollup" in prop:
        r = prop["rollup"]
        if r["type"] == "array" and r["array"]:
            first = r["array"][0]
            for key in ("title","rich_text","text"):
                if key in first and first[key]:
                    return first[key][0].get("plain_text","")
            if "number" in first and first["number"] is not None: return str(first["number"])
            if "date" in first and first["date"]: return first["date"]["start"]
            return ""
        if r["type"] == "number": return "" if r["number"] is None else str(r["number"])
    if "relation" in prop and prop["relation"]:
        return prop["relation"][0].get("id","")
    if "unique_id" in prop:
        pfx = prop["unique_id"].get("prefix") or ""; num = prop["unique_id"].get("number") or ""
        return f"{pfx}{num}"
    return ""

def format_inr_number(x: float) -> str:
    # simple formatting; keeps it consistent in templates
    try:
        return f"{x:,.2f}".rstrip("0").rstrip(".")
    except:
        return str(x)
        
def fetch_loan_page_values(loan_page_id: str) -> dict:
    r = requests.get(f"{NOTION_API}/pages/{loan_page_id}", headers=notion_headers(), timeout=90)
    if r.status_code >= 300:
        raise RuntimeError(f"Get page failed: {r.status_code} {r.text}")

    p = r.json().get("properties", {})
    g = lambda k: parse_field(p.get(k, {}))

    data = {
        "Loan_Application_ID": g("Loan Application ID"),
        "Borrower_Name": g("Full Name"),
        "Co_Borrower_Name": g("Co-borrower"),
        "Loan_Type": g("Loan Type"),
        "Sanction_Date": g("Sanction Date"),

        "Amount_Sanctioned": g("Amount Sanctioned"),
        "Tenure": g("Tenure (Days)"),
        "Interest_Rate": g("Interest Rate (Yearly)"),
        "EMI_Frequency": g("Repayment Frequency") or g("Frequency"),
        "EMI_Amount": g("EMI Amount"),

        # this will be overwritten below
        "Total_Repayable_Amount": g("Outstanding Amount "),

        "First_EMI_Date": g("Start Date"),
        "Last_EMI_Date": g("End Date"),

        "Processing_Fee": g("Processing_Fee"),
        "Processing_Fee_Amount": g("Processing Fee Amount"),

        "Insurance_Fee": g("Insurance_Fee"),
        "Stamp_Duty": g("Stamp_Duty"),
        "Foreclosure_Charges": g("Foreclosure_Clauses"),

        "Disbursement_Date": g("Disbursement Date"),
        "Bank_Account_Details": g("Bank_Account_Details"),
        "Mode": g("Mode"),
        "Mandate_Status": g("Mandate_Status"),
        "Credit_Officer_Name": g("Credit Officer Assigned"),
    }

    # ✅ Compute Total_Repayable_Amount = EMI_Amount * Tenure
    emi = _parse_money_to_float(data.get("EMI_Amount"))
    tenure = int(_parse_money_to_float(data.get("Tenure")))  # tenure as count
    total = emi * tenure
    data["Total_Repayable_Amount"] = format_inr_number(total)

    return data



# -------------------------------------------------------------------
# HTML → PDF (Playwright)
# -------------------------------------------------------------------
def ensure_chromium_installed():
    chromium_path = "/opt/render/.cache/ms-playwright/chromium-1129/chrome-linux/chrome"
    if not os.path.exists(chromium_path):
        subprocess.run(["python", "-m", "playwright", "install", "chromium"], check=True)
    return chromium_path

def html_to_pdf_bytes(html_str: str) -> bytes:
    ensure_chromium_installed()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_str)
        tmp_html = f.name
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()
        page.goto("file://" + tmp_html, wait_until="domcontentloaded", timeout=60000)
        pdf_bytes = page.pdf(format="A4", print_background=True)
        browser.close()
    os.remove(tmp_html)
    return pdf_bytes

# -------------------------------------------------------------------
# Rendering helpers
# -------------------------------------------------------------------

def _parse_money_to_float(x) -> float:
    """
    Accepts: 500000, "500000", "5,00,000", "₹5,00,000", "500000.75"
    Returns: 500000.75 (float) or 0.0 if not parseable
    """
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if not s:
        return 0.0
    # keep digits and dot only
    s = re.sub(r"[^0-9.]", "", s)
    if s.count(".") > 1:
        # if messy, remove all dots except last
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(s) if s else 0.0
    except:
        return 0.0


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
_TEENS = ["Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

def _two_digit_words(n: int) -> str:
    if n == 0:
        return ""
    if n < 10:
        return _ONES[n]
    if 10 <= n < 20:
        return _TEENS[n - 10]
    t, o = divmod(n, 10)
    return _TENS[t] + ("" if o == 0 else f" {_ONES[o]}")

def _three_digit_words(n: int) -> str:
    h, r = divmod(n, 100)
    parts = []
    if h:
        parts.append(f"{_ONES[h]} Hundred")
    if r:
        parts.append(_two_digit_words(r))
    return " ".join(parts).strip()

def indian_number_to_words(n: int) -> str:
    if n == 0:
        return "Zero"
    if n < 0:
        return "Minus " + indian_number_to_words(-n)

    # Indian groups: last 3 digits, then 2-digit groups (Thousand, Lakh, Crore, Arab, Kharab...)
    scales = ["", "Thousand", "Lakh", "Crore", "Arab", "Kharab"]
    parts = []

    last3 = n % 1000
    n //= 1000
    if last3:
        parts.append(_three_digit_words(last3))

    scale_idx = 1
    while n > 0 and scale_idx < len(scales):
        grp = n % 100
        n //= 100
        if grp:
            parts.append(f"{_two_digit_words(grp)} {scales[scale_idx]}".strip())
        scale_idx += 1

    return " ".join(reversed([p for p in parts if p])).strip()

def amount_to_inr_words(amount_any) -> str:
    amt = _parse_money_to_float(amount_any)
    rupees = int(amt)
    paise = int(round((amt - rupees) * 100))

    rupee_words = indian_number_to_words(rupees)
    if paise > 0:
        paise_words = indian_number_to_words(paise)
        return f"{rupee_words} Rupees and {paise_words} Paise Only"
    return f"{rupee_words} Rupees Only"


def render_kfs_html(data: dict, extra: dict | None = None) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    tpl = env.get_template(KFS_TEMPLATE_FILENAME)
    ctx = dict(data)
    if extra: ctx.update(extra)
    return tpl.render(ctx)

def render_contract_html(data: dict, extra: dict | None = None) -> str:
    env = Environment(loader=FileSystemLoader(CONTRACTS_DIR), autoescape=False)
    try:
        tpl = env.get_template(CONTRACT_TEMPLATE_FILENAME)
    except TemplateNotFound:
        raise RuntimeError(f"Contract template not found at {CONTRACT_TEMPLATE_PATH}")
    ctx = dict(data)
    if extra:
        ctx.update(extra)
    return tpl.render(ctx)

# -------------------------------------------------------------------
# Signature utils
# -------------------------------------------------------------------
def decode_data_url_png(data_url: str) -> bytes:
    if not data_url or "," not in data_url: raise RuntimeError("Invalid signature data.")
    return base64.b64decode(data_url.split(",", 1)[1])

def stamp_signature_at_point(pdf_bytes: bytes, signature_png: bytes, attn_text: str,
                             page_index: int = 0, x_pt: float = 420, y_pt: float = 100, width_pt: float = 220) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if page_index >= len(reader.pages):
        page_index = max(0, len(reader.pages) - 1)
    page = reader.pages[page_index]
    pw, ph = float(page.mediabox.width), float(page.mediabox.height)
    sig_w = width_pt; sig_h = sig_w * 0.33
    x = max(6, min(x_pt, pw - sig_w - 6))
    y = max(6, min(y_pt, ph - sig_h - 6))
    overlay_stream = io.BytesIO()
    c = rl_canvas.Canvas(overlay_stream, pagesize=(pw, ph))
    img = ImageReader(io.BytesIO(signature_png))
    c.drawImage(img, x, y, width=sig_w, height=sig_h, mask='auto')
    c.setFont("Helvetica", 9); c.setFillGray(0.2)
    c.drawString(x, y - 12, attn_text[:140])
    c.showPage(); c.save()
    overlay_pdf = PdfReader(io.BytesIO(overlay_stream.getvalue()))
    page.merge_page(overlay_pdf.pages[0])
    out = PdfWriter()
    for p in reader.pages: out.add_page(p)
    out_buf = io.BytesIO(); out.write(out_buf)
    return out_buf.getvalue()

# -------------------------------------------------------------------
# Small shared helpers (forms)
# -------------------------------------------------------------------
def form_fields(fields_def):
    return [{**f, "id": f["notion_prop"]} for f in fields_def]

def validate(req, fields):
    errors, clean = {}, {}
    for f in fields:
        fid = f["id"]; ftype = f["type"]; required = f.get("required", False)
        if ftype == "multi_select":
            raw = req.form.getlist(fid)
        elif ftype == "files":
            raw = req.files.getlist(fid)
        elif ftype == "relation_session":
            raw = None
        else:
            raw = req.form.get(fid)
        if required and ftype != "relation_session":
            missing = (
                (ftype == "multi_select" and len(raw) == 0) or
                (ftype == "files" and all((not fs or not getattr(fs, "filename", "")) for fs in (raw or []))) or
                (ftype not in ["multi_select", "files"] and (raw is None or str(raw).strip() == ""))
            )
            if missing:
                errors[fid] = "This field is required."
                clean[fid] = raw
                continue
        clean[fid] = raw
    return clean, errors

# -------------------------------------------------------------------
# PAGES 1–5 (Borrower, Field Verification, Risk Remarks, Loan Application, Income Assessment)
# -------------------------------------------------------------------
from schema import FIELDS
from schema_page2 import FIELDS_PAGE2
from schema_page3 import FIELDS_PAGE3
from schema_page4 import FIELDS_PAGE4
from schema_page5 import FIELDS_PAGE5

@app.route("/", methods=["GET","POST"])
def form():
    fields = form_fields(FIELDS)
    errors, success_id = {}, None
    try:
        if request.method == "POST":
            clean, errors = validate(request, fields)
            if not errors:
                props = {}
                for f in fields:
                    v = clean.get(f["id"])
                    t = f["type"]; name = f["notion_prop"]
                    if t == "title":
                        props[name] = {"title": [{"type": "text", "text": {"content": (v or "")}}]}
                    elif t == "number":
                        props[name] = {"number": float(v) if v not in (None,"") else None}
                    elif t == "date":
                        props[name] = {"date": {"start": v}} if v else {"date": None}
                    elif t == "select":
                        props[name] = {"select": {"name": v}} if v else {"select": None}
                    elif t == "multi_select":
                        props[name] = {"multi_select": [{"name": x} for x in (v or [])]}
                    elif t == "checkbox":
                        props[name] = {"checkbox": (v == "on" or v is True)}
                    elif t == "url":
                        props[name] = {"url": v or None}
                    elif t == "email":
                        props[name] = {"email": v or None}
                    elif t == "phone":
                        props[name] = {"phone_number": v or None}
                    elif t == "rich_text":
                        props[name] = {"rich_text": [{"type":"text","text":{"content": v or ""}}]}
                    elif t == "files":
                        files_arr = []
                        for fs in (v or []):
                            if fs and getattr(fs, "filename", ""):
                                init = requests.post(f"{NOTION_API}/file_uploads",
                                                     headers=notion_headers(),
                                                     json={"filename": fs.filename, "mode": "single_part"})
                                init.raise_for_status()
                                up_id = init.json()["id"]
                                send = requests.post(f"{NOTION_API}/file_uploads/{up_id}/send",
                                                     headers=notion_headers(json=False),
                                                     files={"file": (fs.filename, fs, fs.mimetype or "application/octet-stream")})
                                send.raise_for_status()
                                files_arr.append({"name": fs.filename, "type": "file_upload", "file_upload": {"id": up_id}})
                        props[name] = {"files": files_arr}
                    else:
                        props[name] = {"rich_text": [{"type":"text","text":{"content": str(v) if v is not None else ""}}]}
                r = requests.post(f"{NOTION_API}/pages", headers=notion_headers(), json={
                    "parent": {"database_id": NOTION_DATABASE_ID},
                    "properties": props
                }, timeout=90)
                if r.status_code >= 300:
                    errors["__all__"] = f"Notion error: {r.status_code} {r.text}"
                else:
                    success_id = r.json().get("id")
                    session["notion_page_id"] = success_id
                    # save Borrower Name entered by user
                    for f in fields:
                        if f.get("type") == "title" and f.get("name") in ("Borrower Name", "Customer Name"):
                            nm = request.form.get(f["notion_prop"], "").strip()
                            session["borrower_name"] = nm
                            session["borrower_name_actual"] = nm
                    return redirect(url_for("form_page2"))
    except Exception as e:
        errors["__all__"] = f"{type(e).__name__}: {e}"
    return render_template("form.html", title="Borrower Information", fields=fields,
                           errors=errors, success=False, success_id=success_id,
                           csrf_token=secrets.token_hex(16))

@app.route("/page2", methods=["GET","POST"])
def form_page2():
    fields = form_fields(FIELDS_PAGE2)
    errors, success_id = {}, None
    linked_id = session.get("notion_page_id"); borrower_name = session.get("borrower_name")
    try:
        if request.method == "POST":
            clean, errors = validate(request, fields)
            if not errors:
                props = {}
                for f in fields:
                    fid, ftype = f["id"], f["type"]; name = f["notion_prop"]
                    if ftype == "relation_session":
                        if not linked_id:
                            errors["__all__"] = "Missing borrower link. Submit Page 1 first."
                            break
                        props[name] = {"relation": [{"id": linked_id}]}
                    else:
                        v = clean.get(fid)
                        if ftype == "date":
                            props[name] = {"date": {"start": v}} if v else {"date": None}
                        elif ftype == "datetime":
                            props[name] = {"date": {"start": v}} if v else {"date": None}
                        elif ftype == "number":
                            props[name] = {"number": float(v) if v not in (None,"") else None}
                        elif ftype == "select":
                            props[name] = {"select": {"name": v}} if v else {"select": None}
                        elif ftype == "checkbox":
                            props[name] = {"checkbox": (v == "on" or v is True)}
                        elif ftype == "url":
                            props[name] = {"url": v if v else None}
                        elif ftype == "rich_text":
                            props[name] = {"rich_text": [{"type":"text","text":{"content": v or ""}}]}
                        else:
                            props[name] = {"rich_text": [{"type":"text","text":{"content": str(v) if v is not None else ""}}]}
                if not errors:
                    r = requests.post(f"{NOTION_API}/pages", headers=notion_headers(), json={
                        "parent": {"database_id": NOTION_DATABASE_ID_PAGE2}, "properties": props
                    }, timeout=90)
                    if r.status_code >= 300:
                        errors["__all__"] = f"Notion error: {r.status_code} {r.text}"
                    else:
                        success_id = r.json().get("id")
                        session["verification_page_id"] = success_id
                        return redirect(url_for("form_page3"))
    except Exception as e:
        errors["__all__"] = f"{type(e).__name__}: {e}"
    return render_template("form.html", title="Field Verification", subtitle="Step 2",
                           fields=fields, errors=errors, success=False, success_id=success_id,
                           csrf_token=secrets.token_hex(16), linked_id=linked_id, borrower_name=borrower_name)

@app.route("/page3", methods=["GET","POST"])
def form_page3():
    fields = form_fields(FIELDS_PAGE3)
    errors, success_id = {}, None
    linked_id = session.get("notion_page_id"); borrower_name = session.get("borrower_name")
    try:
        if request.method == "POST":
            clean, errors = validate(request, fields)
            if not errors:
                props = {}
                for f in fields:
                    fid, ftype = f["id"], f["type"]; name = f["notion_prop"]
                    if ftype == "relation_session":
                        if not linked_id:
                            errors["__all__"] = "Missing borrower link. Submit Page 1 first."
                            break
                        props[name] = {"relation": [{"id": linked_id}]}
                    else:
                        v = clean.get(fid)
                        if ftype == "rich_text":
                            props[name] = {"rich_text":[{"type":"text","text":{"content": v or ""}}]}
                        elif ftype == "select":
                            props[name] = {"select":{"name": v}} if v else {"select": None}
                        else:
                            props[name] = {"rich_text":[{"type":"text","text":{"content": str(v) if v is not None else ""}}]}
                if not errors:
                    r = requests.post(f"{NOTION_API}/pages", headers=notion_headers(), json={
                        "parent":{"database_id": NOTION_DATABASE_ID_PAGE3}, "properties": props
                    }, timeout=90)
                    if r.status_code >= 300:
                        errors["__all__"] = f"Notion error: {r.status_code} {r.text}"
                    else:
                        success_id = r.json().get("id")
                        session["risk_remarks_page_id"] = success_id
                        return redirect(url_for("form_page4"))
    except Exception as e:
        errors["__all__"] = f"{type(e).__name__}: {e}"
    return render_template("form.html", title="Risk Remarks", subtitle="Step 3",
                           fields=fields, errors=errors, success=False, success_id=success_id,
                           csrf_token=secrets.token_hex(16), linked_id=linked_id, borrower_name=borrower_name)

@app.route("/page4", methods=["GET","POST"])
def form_page4():
    fields = form_fields(FIELDS_PAGE4)
    errors, success_id = {}, None
    linked_id = session.get("notion_page_id"); borrower_name = session.get("borrower_name")
    try:
        if request.method == "POST":
            clean, errors = validate(request, fields)
            if not errors:
                props = {}
                for f in fields:
                    fid, ftype = f["id"], f["type"]; name = f["notion_prop"]
                    if ftype == "relation_session":
                        if not linked_id:
                            errors["__all__"] = "Missing borrower link. Submit Page 1 first."
                            break
                        props[name] = {"relation":[{"id": linked_id}]}
                    elif ftype in ("date", "datetime"):
                        v = clean.get(fid); props[name] = {"date": {"start": v}} if v else {"date": None}
                    elif ftype == "number":
                        v = clean.get(fid); props[name] = {"number": float(v) if v not in (None,"") else None}
                    elif ftype == "select":
                        v = clean.get(fid); props[name] = {"select": {"name": v}} if v else {"select": None}
                    elif ftype == "checkbox":
                        v = clean.get(fid); props[name] = {"checkbox": (v == "on" or v is True)}
                    elif ftype == "url":
                        v = clean.get(fid); props[name] = {"url": v if v else None}
                    elif ftype == "rich_text":
                        v = clean.get(fid); props[name] = {"rich_text":[{"type":"text","text":{"content": v or ""}}]}
                    else:
                        v = clean.get(fid); props[name] = {"rich_text":[{"type":"text","text":{"content": str(v) if v is not None else ""}}]}
                r = requests.post(f"{NOTION_API}/pages", headers=notion_headers(), json={
                    "parent":{"database_id": NOTION_DATABASE_ID_PAGE4}, "properties": props
                }, timeout=90)
                if r.status_code >= 300:
                    errors["__all__"] = f"Notion error: {r.status_code} {r.text}"
                else:
                    success_id = r.json().get("id")
                    session["loan_application_page_id"] = success_id
                    return redirect(url_for("kfs_sign"))
    except Exception as e:
        errors["__all__"] = f"{type(e).__name__}: {e}"
    return render_template("form.html", title="Loan Application Internal", subtitle="Step 4",
                           fields=fields, errors=errors, success=False, success_id=success_id,
                           csrf_token=secrets.token_hex(16), linked_id=linked_id, borrower_name=borrower_name)

# -------------------------------------------------------------------
# KFS preview + submit
# -------------------------------------------------------------------
@app.route("/kfs-sign", methods=["GET"])
@app.route("/kfs-sign", methods=["GET"])
def kfs_sign():
    loan_id = session.get("loan_application_page_id")
    if not loan_id:
        return redirect(url_for("form_page4"))

    try:
        data = fetch_loan_page_values(loan_id)

        # ⭐ If user already typed name earlier in session, overwrite for preview
        signer_preview_name = session.get("borrower_name") or None
        if signer_preview_name:
            data["Borrower_Name"] = signer_preview_name

        # ⭐ Also show correct Processing Fee formula in preview
        if data.get("Processing_Fee_Amount"):
            data["Processing_Fee"] = data["Processing_Fee_Amount"]

        logo_http = url_for("static", filename="ub-portfolio-logo.png")
        kfs_html = render_kfs_html(data, extra={"logo_src": logo_http})

    except Exception as e:
        session["kfs_error"] = f"KFS render failed: {e}"
        return redirect(url_for("form_page5"))

    sign_ctx = {
        "ip": request.headers.get("X-Forwarded-For", request.remote_addr or ""),
        "now_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }

    return render_template(
        "sign_kfs.html",
        title="Review & Sign KFS",
        kfs_html=kfs_html,
        borrower_name=data["Borrower_Name"],
        sign_ctx=sign_ctx
    )


@app.route("/kfs-sign/submit", methods=["POST"])
def kfs_sign_submit():
    loan_id = session.get("loan_application_page_id")
    if not loan_id: return redirect(url_for("form_page4"))
    sig_data_url = request.form.get("sig_data_url","")
    signer_name  = request.form.get("signer_name","").strip()
    signer_email = request.form.get("signer_email","").strip()
    attn_ip      = request.form.get("attn_ip","")
    attn_ts_utc  = request.form.get("attn_ts_utc","")
    if not (sig_data_url and signer_name and signer_email):
        session["kfs_error"] = "Signature, name, and email are required."
        return redirect(url_for("kfs_sign"))
    try:
        data = fetch_loan_page_values(loan_id)

        # ------------------------------------------------------------------
        # ⭐ OVERRIDE BORROWER NAME WITH SIGNER NAME
        # ------------------------------------------------------------------
        data["Borrower_Name"] = signer_name

        # ------------------------------------------------------------------
        # ⭐ USE THE NEW PROCESSING FEE FORMULA FIELD IF AVAILABLE
        # ------------------------------------------------------------------
        if data.get("Processing_Fee_Amount"):
            data["Processing_Fee"] = data["Processing_Fee_Amount"]
        # else fallback to whatever was already there

        # ------------------------------------------------------------------
        # Render KFS with corrected data
        # ------------------------------------------------------------------
        logo_http = url_for("static", filename="ub-portfolio-logo.png", _external=True)
        html = render_kfs_html(data, extra={"logo_src": logo_http})

        pdf = html_to_pdf_bytes(html)
        sig_png = decode_data_url_png(sig_data_url)
        attn_text = f"Signed by {signer_name} <{signer_email}> at {attn_ts_utc} UTC · IP {attn_ip}"

        signed_pdf = stamp_signature_at_point(
            pdf, sig_png, attn_text,
            page_index=KFS_SIG_PAGE_INDEX,
            x_pt=KFS_SIG_X_PT,
            y_pt=KFS_SIG_Y_PT,
            width_pt=KFS_SIG_WIDTH_PT
        )

        pdf_sha256 = hashlib.sha256(signed_pdf).hexdigest()
        fname = f"signed_kfs_{data.get('Loan_Application_ID') or loan_id}.pdf"
        # Upload
        init = requests.post(f"{NOTION_API}/file_uploads", headers=notion_headers(),
                             json={"filename": fname, "mode":"single_part"}, timeout=90)
        init.raise_for_status()
        up_id = init.json()["id"]
        send = requests.post(f"{NOTION_API}/file_uploads/{up_id}/send",
                             headers=notion_headers(json=False),
                             files={"file": (fname, io.BytesIO(signed_pdf), "application/pdf")},
                             timeout=180)
        send.raise_for_status()
        # Patch KFS property (assumes property exists and is files)
        patch = requests.patch(f"{NOTION_API}/pages/{loan_id}",
                               headers=notion_headers(),
                               json={"properties": {
                                   KFS_FILES_PROP_NAME: {"files":[{"name": fname, "type":"file_upload", "file_upload":{"id": up_id}}]},
                                   "Signed By Name": {"rich_text":[{"type":"text","text":{"content": signer_name}}]},
                                   "Signed By Email": {"email": signer_email},
                                   "Signed IP": {"rich_text":[{"type":"text","text":{"content": attn_ip}}]},
                                   "Signed At": {"date":{"start": attn_ts_utc}},
                                   "KFS SHA256": {"rich_text":[{"type":"text","text":{"content": pdf_sha256}}]},
                                   "KFS Signed": {"checkbox": True}
                               }}, timeout=90)
        patch.raise_for_status()
    except Exception as e:
        session["kfs_error"] = f"KFS signing/upload failed: {e}"
    return redirect(url_for("form_page5"))

# -------------------------------------------------------------------
# Page 5 — create Income Assessment, then jump to contract
# -------------------------------------------------------------------
@app.route("/page5", methods=["GET", "POST"])
def form_page5():
    from schema_page5 import FIELDS_PAGE5
    fields = form_fields(FIELDS_PAGE5)
    errors, success = {}, False
    kfs_err = session.pop("kfs_error", None)
    if kfs_err:
        errors["__all__"] = kfs_err

    borrower_id = session.get("notion_page_id")
    borrower_name = session.get("borrower_name")
    loan_app_id = session.get("loan_application_page_id")

    try:
        if request.method == "POST":
            props = {}
            for f in fields:
                sid = session.get(f.get("session_key",""))
                if not sid:
                    errors["__all__"] = f"Missing link for {f['name']}. Please complete prior steps."
                    break
                props[f["notion_prop"]] = {"relation":[{"id": sid}]}
            if not errors:
                r = requests.post(f"{NOTION_API}/pages", headers=notion_headers(),
                                  json={"parent":{"database_id": NOTION_DATABASE_ID_PAGE5},
                                        "properties": props}, timeout=90)
                if r.status_code >= 300:
                    errors["__all__"] = f"Notion error: {r.status_code} {r.text}"
                else:
                    success_id = r.json().get("id")
                    session["income_assessment_page_id"] = success_id
                    # Pass the loan id explicitly
                    return redirect(url_for("contract_sign", loan_id=loan_app_id))
    except Exception as e:
        errors["__all__"] = f"{type(e).__name__}: {e}"

    return render_template("form.html", title="Income Assessment Form", subtitle="Step 5",
                           fields=fields, errors=errors, success=success, success_id=None,
                           csrf_token=secrets.token_hex(16), linked_id=borrower_id, borrower_name=borrower_name)

# -------------------------------------------------------------------
# Contract Sign + Submit
# -------------------------------------------------------------------
@app.route("/contract-sign", methods=["GET"])
def contract_sign():
    try:
        loan_id = request.args.get("loan_id") or session.get("loan_application_page_id")
        if not loan_id:
            return redirect(url_for("form_page4"))
        borrower_name = session.get("borrower_name_actual") or session.get("borrower_name") or "Borrower"
        data = fetch_loan_page_values(loan_id)
        now = datetime.datetime.utcnow()
        amount_val = data.get("Amount_Sanctioned", "0")
        data.update({
            "Borrower_Name": borrower_name,
            "Borrower_Address": session.get("borrower_address", data.get("Address", "N/A")),
            "Borrower_Phone": session.get("borrower_phone", data.get("Phone_Number", "N/A")),
            "Borrower_Guardian": data.get("Guardian_Name", "N/A"),
            "Amount_Sanctioned": data.get("Amount_Sanctioned", "₹0"),
            "Amount_Sanctioned_Words": amount_to_inr_words(amount_val),
            "date": now.strftime("%d"),
            "month": now.strftime("%B"),
            "year": now.strftime("%Y")
        })
        env = Environment(loader=FileSystemLoader(CONTRACTS_DIR), autoescape=False)
        tpl = env.get_template(CONTRACT_TEMPLATE_FILENAME)
        contract_html = tpl.render(data)
    except Exception as e:
        session["kfs_error"] = f"Contract render failed: {e}"
        return redirect(url_for("form_page5"))

    sign_ctx = {"ip": request.headers.get("X-Forwarded-For", request.remote_addr or ""),
                "now_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}
    return render_template("contract_sign.html", title="Review & Sign Loan Agreement",
                           contract_html=contract_html, borrower_name=borrower_name, sign_ctx=sign_ctx)

def safe_patch_contract_properties(loan_id: str, fname: str, up_id: str,
                                   signer_name: str, signer_email: str,
                                   attn_ip: str, attn_ts_utc: str):
    """Patch only properties that exist on page → avoids Notion 400."""
    # Fetch page props
    page_info = requests.get(f"{NOTION_API}/pages/{loan_id}", headers=notion_headers(), timeout=90)
    page_info.raise_for_status()
    props = page_info.json().get("properties", {})
    def has_prop(name, ptype=None):
        if name not in props: return False
        return True if ptype is None else props[name].get("type") == ptype

    patch_props = {}
    if has_prop(CONTRACT_FILES_PROP_NAME, "files"):
        patch_props[CONTRACT_FILES_PROP_NAME] = {
            "files": [{"name": fname, "type":"file_upload", "file_upload":{"id": up_id}}]
        }
    if has_prop("Signed By Name", "rich_text"):
        patch_props["Signed By Name"] = {"rich_text":[{"type":"text","text":{"content": signer_name}}]}
    if has_prop("Signed By Email", "email"):
        patch_props["Signed By Email"] = {"email": signer_email}
    if has_prop("Signed IP", "rich_text"):
        patch_props["Signed IP"] = {"rich_text":[{"type":"text","text":{"content": attn_ip}}]}
    if has_prop("Signed At", "date"):
        patch_props["Signed At"] = {"date":{"start": attn_ts_utc}}
    if has_prop("Contract Signed", "checkbox"):
        patch_props["Contract Signed"] = {"checkbox": True}

    if not patch_props:
        # Print available props to help you align names/types
        print("❌ No matching properties on page to patch. Page properties were:")
        for k, v in props.items(): print(f" - {k}: {v.get('type')}")
        raise RuntimeError("No matching properties to patch on this Notion page.")

    payload = {"properties": patch_props}
    print("Patch payload (contract):", json.dumps(payload, indent=2))
    patch = requests.patch(f"{NOTION_API}/pages/{loan_id}",
                           headers=notion_headers(), json=payload, timeout=90)
    if patch.status_code >= 400:
        print("❌ Notion patch error:", patch.status_code, patch.text)
    patch.raise_for_status()
    print("✅ Contract uploaded and properties updated.")

@app.route("/contract-sign/submit", methods=["POST"])
def contract_sign_submit():
    # Make sure we patch the Loan Application page (not borrower/other)
    loan_id = session.get("loan_application_page_id")
    borrower_id = session.get("notion_page_id")

    if not loan_id or loan_id == borrower_id:
        print("⚠️ loan_application_page_id missing or incorrect, finding latest Loan Application page...")
        try:
            # CHANGE "Borrower" to your actual relation property name in Loan Application DB
            query = {
                "filter": {"property": "Borrower", "relation": {"contains": borrower_id}},
                "page_size": 1,
                "sorts": [{"timestamp": "created_time", "direction": "descending"}]
            }
            r = requests.post(f"{NOTION_API}/databases/{NOTION_DATABASE_ID_PAGE4}/query",
                              headers=notion_headers(), json=query, timeout=90)
            r.raise_for_status()
            results = r.json().get("results", [])
            if results:
                loan_id = results[0]["id"]
                session["loan_application_page_id"] = loan_id
                print("✅ Found linked Loan Application page:", loan_id)
            else:
                print("⚠️ No linked Loan Application found for this borrower.")
                session["kfs_error"] = "Could not locate Loan Application page in Notion."
                return redirect(url_for("form_page5"))
        except Exception as e:
            print("⚠️ Failed to fetch Loan Application page:", e)
            session["kfs_error"] = "Could not locate Loan Application page in Notion."
            return redirect(url_for("form_page5"))

    sig_data_url = request.form.get("sig_data_url", "")
    signer_name = request.form.get("signer_name", "").strip()
    signer_email = request.form.get("signer_email", "").strip()
    attn_ip = request.form.get("attn_ip", "")
    attn_ts_utc = request.form.get("attn_ts_utc", "")
    if not (sig_data_url and signer_name and signer_email):
        session["kfs_error"] = "Signature, name, and email are required."
        return redirect(url_for("contract_sign"))

    try:
        data = fetch_loan_page_values(loan_id)
        borrower_name = session.get("borrower_name_actual") or session.get("borrower_name") or data.get("Borrower_Name", "Borrower")
        now = datetime.datetime.utcnow()
        amount_val = data.get("Amount_Sanctioned", "0")
        context = {
            "Borrower_Name": borrower_name,
            "Borrower_Address": session.get("borrower_address", data.get("Address", "N/A")),
            "Borrower_Phone": session.get("borrower_phone", data.get("Phone_Number", "N/A")),
            "Amount_Sanctioned": data.get("Amount_Sanctioned", ""),
            "Amount_Sanctioned_Words": amount_to_inr_words(amount_val),
            "date": now.strftime("%d"),
            "month": now.strftime("%B"),
            "year": now.strftime("%Y"),
        }

        contract_html = render_contract_html(context)
        pdf = html_to_pdf_bytes(contract_html)
        sig_png = decode_data_url_png(sig_data_url)
        attn_text = f"Signed by {signer_name} <{signer_email}> at {attn_ts_utc} UTC · IP {attn_ip}"
        signed_pdf = stamp_signature_at_point(pdf, sig_png, attn_text,
                                              page_index=CONTRACT_SIG_PAGE_INDEX,
                                              x_pt=CONTRACT_SIG_X_PT,
                                              y_pt=CONTRACT_SIG_Y_PT,
                                              width_pt=CONTRACT_SIG_WIDTH_PT)

        fname = f"signed_loan_agreement_{loan_id}.pdf"
        init = requests.post(f"{NOTION_API}/file_uploads", headers=notion_headers(),
                             json={"filename": fname, "mode": "single_part"}, timeout=90)
        init.raise_for_status()
        up_id = init.json()["id"]
        send = requests.post(f"{NOTION_API}/file_uploads/{up_id}/send",
                             headers=notion_headers(json=False),
                             files={"file": (fname, io.BytesIO(signed_pdf), "application/pdf")},
                             timeout=180)
        send.raise_for_status()

        # SAFE PATCH (build only existing properties)
        safe_patch_contract_properties(loan_id, fname, up_id, signer_name, signer_email, attn_ip, attn_ts_utc)

    except Exception as e:
        session["kfs_error"] = f"Contract signing/upload failed: {e}"
        return redirect(url_for("form_page5"))

    return redirect(url_for("thank_you"))

# -------------------------------------------------------------------
# Thank You
# -------------------------------------------------------------------
@app.route("/thank-you", methods=["GET"])
def thank_you():
    return render_template("thank_you.html",
                           title="Thank you!",
                           borrower_name=session.get("borrower_name"),
                           loan_id=session.get("loan_application_page_id"))

# -------------------------------------------------------------------
# Ledger endpoints (unchanged from your code)
# -------------------------------------------------------------------
def fetch_df_from_notion(db_id: str, date_prop: str, amt_prop: str, date_from=None, date_to=None) -> pd.DataFrame:
    flt = None
    if date_from or date_to:
        cond = {}
        if date_from: cond["on_or_after"] = pd.to_datetime(date_from).date().isoformat()
        if date_to:   cond["on_or_before"] = pd.to_datetime(date_to).date().isoformat()
        flt = {"property": date_prop, "date": cond}
    rows = query_notion_db(db_id, filter_block=flt, sorts=[{"property": date_prop, "direction": "ascending"}])
    out = []
    for pg in rows:
        props = pg.get("properties", {})
        d = extract_date(props.get(date_prop, {}))
        a = None
        ap = props.get(amt_prop, {})
        # Support number & rich_text fallback
        if "number" in ap and ap["number"] is not None:
            a = float(ap["number"])
        elif "rich_text" in ap and ap["rich_text"]:
            try: a = float(ap["rich_text"][0]["plain_text"].replace(",", "")) 
            except: a = None
        if d is not None and a is not None:
            out.append({"Date": d, "Amount": a})
    if not out:
        return pd.DataFrame(columns=["Date","Amount"])
    return pd.DataFrame(out).groupby("Date", as_index=False)["Amount"].sum()

def build_ledger(disb_df: pd.DataFrame, coll_df: pd.DataFrame, start_corpus: float, rng_start=None, rng_end=None) -> pd.DataFrame:
    import datetime as dt
    if disb_df.empty and coll_df.empty and not rng_start and not rng_end:
        return pd.DataFrame(columns=["Date", "Deployed", "Collected", "Net Inflow (Day)", "Corpus Remaining"])
    mins = []
    if not disb_df.empty and pd.notna(disb_df["Date"].min()): mins.append(pd.to_datetime(disb_df["Date"].min()).date())
    if not coll_df.empty and pd.notna(coll_df["Date"].min()): mins.append(pd.to_datetime(coll_df["Date"].min()).date())
    if rng_start: mins.append(pd.to_datetime(rng_start).date())
    min_date = mins[0] if mins else dt.date.today()
    for d in mins:
        if d < min_date: min_date = d
    maxs = [pd.to_datetime(rng_end).date()] if rng_end else [dt.date.today()]
    if not disb_df.empty and pd.notna(disb_df["Date"].max()): maxs.append(pd.to_datetime(disb_df["Date"].max()).date())
    if not coll_df.empty and pd.notna(coll_df["Date"].max()): maxs.append(pd.to_datetime(coll_df["Date"].max()).date())
    max_date = maxs[0]
    for d in maxs:
        if d > max_date: max_date = d
    if max_date < min_date: max_date = min_date
    calendar = pd.DataFrame({"Date": pd.date_range(min_date, max_date, freq="D").date})
    disb_daily = (disb_df.rename(columns={"Amount": "Deployed"}) if not disb_df.empty else pd.DataFrame(columns=["Date", "Deployed"]))
    coll_daily = (coll_df.rename(columns={"Amount": "Collected"}) if not coll_df.empty else pd.DataFrame(columns=["Date", "Collected"]))
    tr = calendar.merge(disb_daily, on="Date", how="left").merge(coll_daily, on="Date", how="left")
    tr[["Deployed", "Collected"]] = tr[["Deployed", "Collected"]].fillna(0.0)
    tr["Net Inflow (Day)"] = tr["Collected"] - tr["Deployed"]
    tr["_cum_disbursed"]  = tr["Deployed"].cumsum()
    tr["_cum_collected"]  = tr["Collected"].cumsum()
    tr["_outstanding"]    = tr["_cum_disbursed"] - tr["_cum_collected"]
    tr["Corpus Remaining"] = start_corpus - tr["_outstanding"]
    cols = ["Date", "Deployed", "Collected", "Net Inflow (Day)", "Corpus Remaining"]
    return tr[cols]

@app.route("/export-ledger", methods=["GET"])
def export_ledger():
    # (same as your version; omitted here for brevity – keep your implementation)
    return "Ledger UI here (unchanged)."

# -------------------------------------------------------------------
# Debug helpers (optional)
# -------------------------------------------------------------------
@app.route("/debug/loan-app-props")
def debug_loan_app_props():
    try:
        r = requests.get(f"{NOTION_API}/databases/{NOTION_DATABASE_ID_PAGE4}", headers=notion_headers(), timeout=90)
        r.raise_for_status()
        props = r.json().get("properties", {})
        lines = [f"{k} → {v.get('type')}" for k, v in props.items()]
        return "<pre>" + "\n".join(lines) + "</pre>"
    except Exception as e:
        return f"Error: {e}", 500

# -------------------------------------------------------------------
# Run
# -------------------------------------------------------------------
if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.getenv("PORT", "10000"))
    url = f"http://{host}:{port}/"
    print("\n================= Flask Dev Server =================")
    print(f"→ Page 1 (Borrower): {url}")
    print(f"→ Page 2:            {url}page2")
    print(f"→ Page 3:            {url}page3")
    print(f"→ Page 4:            {url}page4")
    print(f"→ KFS Sign:          {url}kfs-sign")
    print(f"→ Page 5:            {url}page5")
    print(f"→ Contract Sign:     {url}contract-sign")
    print(f"→ Ledger:            {url}export-ledger")
    print("====================================================\n", flush=True)
    app.run(host=host, port=port, debug=False)