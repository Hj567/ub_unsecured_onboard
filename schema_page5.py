# schema_page5.py
# Page 5: all three are RELATION fields (auto-linked from saved session IDs)

FIELDS_PAGE5 = [
    # Customer Name -> Borrower (Page 1)
    {"name": "Customer Name", "type": "relation_session", "notion_prop": "Customer Name",
     "session_key": "notion_page_id", "help": "Auto-linked to borrower from Page 1."},

    # Field Verification -> Page 2
    {"name": "Field Verification", "type": "relation_session", "notion_prop": "Field Verification",
     "session_key": "verification_page_id", "help": "Auto-linked to Field Verification page."},

    # Loan Application -> Page 4
    {"name": "Loan Application", "type": "relation_session", "notion_prop": "Loan Application",
     "session_key": "loan_application_page_id", "help": "Auto-linked to the Loan Application page."},
]
