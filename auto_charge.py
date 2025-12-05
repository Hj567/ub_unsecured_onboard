import os
import json
from datetime import date
from uuid import uuid4

import requests
from requests.auth import HTTPBasicAuth

# -------------------------------------------------------------------
# CONFIG – ENV VARS (DO NOT hard-code secrets)
# -------------------------------------------------------------------

RAZORPAY_KEY_ID = "rzp_live_RmhBQY0fhwdaM5"
RAZORPAY_KEY_SECRET = "1xlKDlEeoLolPGAekPuxcEJZ"

NOTION_TOKEN = "ntn_m753053303634rFIHwUa6VYWOqSLtZm7lNXVpUCVNoi53P"
NOTION_DB_ID = "2041c0dad0ac80ff874af469a7cf2d44"


RAZORPAY_BASE = "https://api.razorpay.com/v1"

if not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET):
    raise RuntimeError("Razorpay keys not set. Define RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.")

if not (NOTION_TOKEN and NOTION_DB_ID):
    raise RuntimeError("Notion credentials not set. Define NOTION_TOKEN and NOTION_DB_ID.")

auth = HTTPBasicAuth(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# constant email as requested
FIXED_EMAIL = "ubportfolio73@gmail.com"

# ===========================================================
# NOTION HELPERS
# ===========================================================
def notion_query_database():
    """
    Fetch all pages from the Notion database (handles pagination).
    """
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    payload = {}

    results = []
    has_more = True
    start_cursor = None

    while has_more:
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = requests.post(url, headers=NOTION_HEADERS, data=json.dumps(payload))
        if resp.status_code != 200:
            raise RuntimeError(f"Notion query failed: {resp.status_code} - {resp.text}")

        data = resp.json()
        results.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return results


def get_text_property(props, name):
    """
    Extract plain text from a title or rich_text property.
    Returns None if property is missing or empty.
    """
    if name not in props:
        return None
    p = props[name]

    if p["type"] == "title":
        arr = p["title"]
        if not arr:
            return None
        return "".join([t["plain_text"] for t in arr])

    if p["type"] == "rich_text":
        arr = p["rich_text"]
        if not arr:
            return None
        return "".join([t["plain_text"] for t in arr])

    return None


def get_formula_number_property(props, name):
    """
    Extract a numeric value from a formula property (for EMI Amount).
    """
    if name not in props:
        return None
    p = props[name]
    if p["type"] != "formula":
        return None
    f = p["formula"]
    if f["type"] == "number":
        return f["number"]
    return None


def get_rollup_customer_id(props, name):
    """
    Extract a readable Customer ID from a rollup of unique_id.

    From your debug:
      "Customer ID": type=rollup → rollup.type=array → item.type="unique_id"

    unique_id:
      { "prefix": null or "ABC", "number": 57 }

    We convert to:
      - "ABC57" if prefix exists
      - "57" if prefix is null
    """
    if name not in props:
        return None
    p = props[name]
    if p["type"] != "rollup":
        return None

    roll = p["rollup"]
    if roll["type"] != "array":
        return None

    arr = roll["array"]
    if not arr:
        return None

    item = arr[0]
    if item["type"] == "unique_id":
        uid = item["unique_id"]
        prefix = uid.get("prefix")
        number = uid.get("number")
        if prefix:
            return f"{prefix}{number}"
        return str(number) if number is not None else None

    # Fallbacks if you change rollup later:
    if item["type"] == "title":
        return "".join(t["plain_text"] for t in item["title"])
    if item["type"] == "rich_text":
        return "".join(t["plain_text"] for t in item["rich_text"])
    if item["type"] == "number":
        return str(item["number"])

    return None


def get_rollup_phone(props, name):
    """
    Extract phone number from a rollup like 'Phone_Number'
    that contains phone_number items.
    """
    if name not in props:
        return None
    p = props[name]
    if p["type"] != "rollup":
        return None

    roll = p["rollup"]
    if roll["type"] != "array":
        return None

    arr = roll["array"]
    if not arr:
        return None

    for item in arr:
        if item["type"] == "phone_number":
            return item["phone_number"]
    return None


def debug_print_sample_pages(limit=3):
    """
    Debug helper: print first few pages from Notion with property names + types.
    """
    print("\n=== Debug: Sample Notion rows ===")
    pages = notion_query_database()
    print(f"Total pages: {len(pages)}")
    for i, page in enumerate(pages[:limit]):
        print(f"\n--- Page {i+1} / {limit} ---")
        print("page_id:", page["id"])
        props = page["properties"]
        for name, p in props.items():
            print(f"  {name}: type={p['type']}  raw={json.dumps(p, indent=2)[:220]}...")


# ===========================================================
# RAZORPAY HELPERS (per recurring docs)
# ===========================================================
def create_order(amount_paise, token_id=None):
    """
    Create a Razorpay order before charging the token.

    POST /orders
    """
    url = f"{RAZORPAY_BASE}/orders"

    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "payment_capture": True,
        "receipt": f"emi_{date.today().isoformat()}_{uuid4().hex[:8]}",
        "notes": {
            "purpose": "Daily EMI token charge",
        },
        # Optional: manual pre-debit control via "notification" object
    }

    resp = requests.post(url, auth=auth, json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"Create order failed: {resp.status_code} - {resp.text}")

    data = resp.json()
    return data["id"]  # order_id


def create_recurring_payment(
    *,
    email: str,
    contact: str,
    amount_inr: float,
    order_id: str,
    customer_id: str,
    token_id: str,
    description: str,
):
    """
    Create a recurring payment as per docs:

    POST /payments/create/recurring
    """
    url = f"{RAZORPAY_BASE}/payments/create/recurring"

    amount_paise = int(round(float(amount_inr) * 100))

    # contact is documented as integer, we'll try to cast
    try:
        contact_int = int("".join(ch for ch in contact if ch.isdigit()))
    except Exception:
        contact_int = contact  # fallback

    payload = {
        "email": email,
        "contact": contact_int,
        "amount": amount_paise,
        "currency": "INR",
        "order_id": order_id,
        "customer_id": customer_id,
        "token": token_id,
        "recurring": True,
        "description": description,
        "notes": {
            "source": "emi_daily_script",
        },
    }

    resp = requests.post(url, auth=auth, json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"Create recurring payment failed: {resp.status_code} - {resp.text}")

    return resp.json()


# ===========================================================
# MAIN DAILY RUN
# ===========================================================
def main():
    print("Fetching rows from Notion...")
    pages = notion_query_database()
    print(f"Found {len(pages)} rows in Notion DB")

    success = []
    failed = []

    for page in pages:
        props = page["properties"]
        page_id = page["id"]

        # A readable loan identifier for logs: "ID" (UBMF-xx)
        loan_id = get_text_property(props, "ID")

        # ----------------- FIELD MAPPING ------------------

        # EMI Amount: formula → number
        emi_amount = get_formula_number_property(props, "EMI Amount")

        # Razorpay token: rich_text (may be empty)
        token_id = get_text_property(props, "enach_token")

        # Razorpay customer_id: from "Customer_ID" rich_text (cust_...)
        razorpay_customer_id = get_text_property(props, "Customer_ID")

        # Optional: 'Repayment Status' formula → "Active" / etc.
        repayment_status = None
        if "Repayment Status" in props and props["Repayment Status"]["type"] == "formula":
            rf = props["Repayment Status"]["formula"]
            if rf["type"] == "string":
                repayment_status = rf["string"]

        # Decide if this loan should be charged:
        is_active = (repayment_status == "Active") if repayment_status is not None else True

        # Internal Customer ID (for description only) – rollup unique_id
        customer_id_desc = get_rollup_customer_id(props, "Customer ID")

        # Contact info (phone via rollup)
        phone = get_rollup_phone(props, "Phone_Number")

        # ----------------- FILTER / GUARDS ------------------

        if not is_active:
            print(f"Skipping page {page_id} ({loan_id}) because Repayment Status = {repayment_status}")
            continue

        # Critical fields for API:
        missing = []
        if emi_amount is None:
            missing.append("EMI Amount (formula)")
        if not token_id:
            missing.append("enach_token (rich_text)")
        if not razorpay_customer_id:
            missing.append("Customer_ID (rich_text - must contain Razorpay cust_... id)")
        if not phone:
            missing.append("Phone_Number (rollup phone)")

        if missing:
            print(f"Skipping page {page_id} ({loan_id}) due to missing fields:")
            for m in missing:
                print("  -", m)
            continue

        # ----------------- DESCRIPTION ------------------
        today_str = date.today().strftime("%d-%m-%Y")
        if not customer_id_desc:
            customer_id_desc = "Unknown"

        description = (
            f"EMI payment for {customer_id_desc}\n"
            f"Date - {today_str}"
        )

        # ----------------- RAZORPAY FLOW ------------------

        try:
            amount_inr = emi_amount
            print(f"\nCharging {amount_inr} INR for loan {loan_id}:")
            print(f"  token   = {token_id}")
            print(f"  cust_id = {razorpay_customer_id}")
            print(f"  email   = {FIXED_EMAIL}")
            print(f"  phone   = {phone}")
            print(f"  desc    = {description!r}")

            # Step 1: Create order
            order_id = create_order(int(round(float(amount_inr) * 100)), token_id=token_id)
            print(f"  Created order: {order_id}")

            # Step 2: Create recurring payment
            payment_resp = create_recurring_payment(
                email=FIXED_EMAIL,
                contact=phone,
                amount_inr=amount_inr,
                order_id=order_id,
                customer_id=razorpay_customer_id,
                token_id=token_id,
                description=description,
            )

            pay_id = payment_resp.get("razorpay_payment_id") or payment_resp.get("id")
            success.append((loan_id, token_id, amount_inr, pay_id, "created"))
            print(f"  ✅ Success: payment_id={pay_id}")
        except Exception as e:
            print(f"  ❌ Failed for loan {loan_id}, token {token_id}: {e}")
            failed.append((loan_id, token_id, emi_amount, str(e)))

    print("\n=== Run summary ===")
    print(f"Successful charges: {len(success)}")
    for loan_id, t_id, amt, pay_id, st in success:
        print(f"  {loan_id} | {t_id} | {amt} | {pay_id} | {st}")

    print(f"\nFailed charges: {len(failed)}")
    for loan_id, t_id, amt, err in failed:
        print(f"  {loan_id} | {t_id} | {amt} | ERROR: {err}")


if __name__ == "__main__":
    # debug_print_sample_pages()  # keep handy if schema changes
    main()