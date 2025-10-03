# schema.py

FIELDS = [
    # --- Basic identity ---
    {"name": "Customer Name", "type": "title", "notion_prop": "Customer Name", "required": True},

    {"name": "Gender", "type": "select", "notion_prop": "Gender",
     "options": ["Male", "Female", "Other"], "required": True},

    {"name": "Date of Birth", "type": "date", "notion_prop": "Date of Birth", "required": True},

    {"name": "Phone Number", "type": "phone", "notion_prop": "Phone Number", "required": True},

    {"name": "Marital Status", "type": "select", "notion_prop": "Marital Status",
     "options": ["Married", "Single"]},

    # --- KYC uploads / consents ---
    {"name": "KYC (Aadhaar)", "type": "files", "notion_prop": "KYC (Aadhaar)",
     "max_files": 10, "max_file_size_mb": 100},

    {"name": "PAN / Form 60", "type": "files", "notion_prop": "PAN / Form 60",
     "max_files": 10, "max_file_size_mb": 100},

    {"name": "Photo", "type": "files", "notion_prop": "Photo",
     "max_files": 10, "max_file_size_mb": 100},

    {"name": "KYC Sharing", "type": "checkbox", "notion_prop": "KYC Sharing"},

    {"name": "CKYCR Upload", "type": "checkbox", "notion_prop": "CKYCR Upload"},

    # --- Credit info / ops flags ---
    {"name": "CIC Pull Check", "type": "checkbox", "notion_prop": "CIC Pull Check"},

    # --- Addresses / notes ---
    {"name": "Permanent Address", "type": "rich_text", "notion_prop": "Permanent Address"},

    # DB expects NUMBER here
    {"name": "Loan Consideration", "type": "number", "format": "float", "notion_prop": "Loan Consideration"},

    # DB expects RICH TEXT here
    {"name": "Earning Members", "type": "rich_text", "notion_prop": "Earning Members"},
]
