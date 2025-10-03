import requests
import json
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
import os
import subprocess

NOTION_TOKEN = "ntn_m753053303634rFIHwUa6VYWOqSLtZm7lNXVpUCVNoi53P"
NOTION_DB_ID = "2041c0dad0ac80ff874af469a7cf2d44"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

def fetch_loan_data():
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    res = requests.post(url, headers=HEADERS)
    res.raise_for_status()
    return res.json()["results"]

def parse_field(prop):
    if "title" in prop:
        return prop["title"][0]["plain_text"] if prop["title"] else ""
    if "rich_text" in prop:
        return prop["rich_text"][0]["plain_text"] if prop["rich_text"] else ""
    if "select" in prop and prop["select"]:
        return prop["select"]["name"]
    if "date" in prop and prop["date"]:
        return prop["date"]["start"]
    if "number" in prop:
        return str(prop["number"]) if prop["number"] is not None else ""
    if "formula" in prop:
        f = prop["formula"]
        if f["type"] == "string": return f["string"] or ""
        if f["type"] == "number": return "" if f["number"] is None else str(f["number"])
        if f["type"] == "date": return f["date"]["start"] if f["date"] else ""
    if "rollup" in prop:
        r = prop["rollup"]
        if r["type"] == "array" and r["array"]:
            first = r["array"][0]
            for typ in ["title", "rich_text", "text"]:
                if typ in first and first[typ]:
                    return first[typ][0]["plain_text"]
            if "number" in first and first["number"] is not None:
                return str(first["number"])
            if "date" in first and first["date"]:
                return first["date"]["start"]
            return json.dumps(first)
        elif r["type"] == "number":
            return "" if r["number"] is None else str(r["number"])
    if "relation" in prop and prop["relation"]:
        return prop["relation"][0].get("id", "")
    if "unique_id" in prop:
        prefix = prop["unique_id"].get("prefix", "") or ""
        number = prop["unique_id"].get("number", "")
        return f"{prefix}{number}"
    return ""

def render_kfs_html(data: dict, output_basename="loan_kfs"):
    env = Environment(loader=FileSystemLoader("."))
    # Put the HTML template next to this script as template.html
    template = env.get_template("template.html")
    rendered_html = template.render(data)

    html_file = f"{output_basename}.html"
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(rendered_html)
    print(f"✅ HTML generated: {html_file}")

def generate_kfs_docs():
    loans = fetch_loan_data()
    for idx, loan in enumerate(loans):
        p = loan["properties"]
        def g(field): return parse_field(p.get(field, {}))

        # IMPORTANT: mirrors your current LaTeX fields 1:1
        loan_data = {
            "Loan_Application_ID": g("Loan Application ID"),
            "Borrower_Name": g("Full Name"),
            "Co_Borrower_Name": g("Co-borrower"),
            "Loan_Type": g("Loan Type"),
            "Sanction_Date": g("Sanction Date"),
            "Amount_Sanctioned": g("Amount Sanctioned"),
            "Tenure": g("Tenure (Months)"),
            "Interest_Rate": g("Interest Rate (Yearly)"),
            "EMI_Frequency": g("Frequency"),
            "EMI_Amount": g("EMI Amount"),
            "Total_Repayable_Amount": g("Outstanding Amount "),
            "First_EMI_Date": g("Start Date"),
            "Last_EMI_Date": g("End Date"),
            "Processing_Fee": g("Processing_Fee"),
            "Insurance_Fee": g("Insurance_Fee"),
            "Stamp_Duty": g("Stamp_Duty"),
            "Foreclosure_Charges": g("Foreclosure_Clauses"),
            "Disbursement_Date": g("Disbursement Date"),
            "Bank_Account_Details": g("Bank_Account_Details"),
            "Mode": g("Mode"),
            "Mandate_Status": g("Mandate_Status"),
            "Generated_Date": datetime.today().strftime("%Y-%m-%d"),
            "Credit_Officer_Name": g("Credit Officer Assigned"),
        }

        output_name = f"loan_kfs_{loan_data['Loan_Application_ID'] or idx}"
        render_kfs_html(loan_data, output_name)

if __name__ == "__main__":
    generate_kfs_docs()