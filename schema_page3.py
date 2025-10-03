# schema_page3.py
# Risk Remarks page
FIELDS_PAGE3 = [
    # Relation to the borrower page created on Page 1
    {"name": "Name of Customer", "type": "relation_session", "notion_prop": "Name of Customer",
     "help": "Auto-linked to the borrower created on Page 1."},

    # The actual remark
    {"name": "Risk Remark", "type": "rich_text", "notion_prop": "Risk Remark"},
]
