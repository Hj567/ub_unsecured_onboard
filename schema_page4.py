# schema_page4.py
# Loan Application Internal (Page 4)

FIELDS_PAGE4 = [
    # Relation to borrower (from session)
    {"name": "Full Name", "type": "relation_session", "notion_prop": "Full Name",
     "help": "Auto-linked to the borrower created on Page 1."},

    {"name": "Co-borrower", "type": "rich_text", "notion_prop": "Co-borrower"},

    {"name": "Loan Type", "type": "select", "notion_prop": "Loan Type",
     "options": ["Individual", "Group"]},

    {"name": "Amount Sanctioned", "type": "number", "format": "float", "notion_prop": "Amount Sanctioned"},

    {"name": "Repayment Frequency", "type": "select", "notion_prop": "Repayment Frequency",
     "options": ["Daily", "Monthly", "Weekly"]},

    {"name": "Interest Rate (Yearly)", "type": "number", "format": "float", "notion_prop": "Interest Rate (Yearly)"},

    {"name": "Start Date", "type": "date", "notion_prop": "Start Date"},

    {"name": "Tenure (Months)", "type": "number", "format": "int", "notion_prop": "Tenure (Months)"},

    {"name": "Credit Officer Assigned", "type": "select", "notion_prop": "Credit Officer Assigned",
     "options": ["Name 1", "Name 2"]},  # adjust options to match your Notion property
]
