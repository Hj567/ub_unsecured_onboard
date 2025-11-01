FIELDS_PAGE2 = [
    {"name": "Borrower Name", "type": "relation_session", "notion_prop": "Borrower Name",
     "help": "Auto-linked to the borrower page created on Page 1."},

    {"name": "Verification Type", "type": "select", "notion_prop": "Verification Type",
     "options": ["Residence", "Business", "Both"]},

    {"name": "Timestamp", "type": "datetime", "notion_prop": "Timestamp"},

    {"name": "GPS Coordinates", "type": "rich_text", "notion_prop": "GPS Coordinates"},

    {"name": "Field Officer Name", "type": "rich_text", "notion_prop": "Field Officer Name"},

    {"name": "Address Verified", "type": "select", "notion_prop": "Address Verified",
     "options": ["Yes", "No"]},

     {"name": "Account Number", "type": "number", "notion_prop": "Account Number"},
    
    {"name": "IFSC Code", "type": "rich_text", "notion_prop": "IFSC Code"},

    {"name": "Number of Family Members", "type": "number", "format": "int", "notion_prop": "Number of Family Members"},

    {"name": "Number of Earning Members", "type": "number", "format": "int", "notion_prop": "Number of Earning Members"},

    {"name": "Dependency Ratio", "type": "number", "format": "float", "notion_prop": "Dependency Ratio"},

    {"name": "Housing Type", "type": "select", "notion_prop": "Housing Type",
     "options": ["Owned", "Rented", "Employer-provided", "Relatives"]},

    {"name": "Construction Type", "type": "select", "notion_prop": "Construction Type",
     "options": ["Pucca", "Semi-pucca", "Kuchha"]},

    {"name": "Electricity Connection", "type": "select", "notion_prop": "Electricity Connection",
     "options": ["Yes", "No"]},

    {"name": "Water Source", "type": "select", "notion_prop": "Water Source",
     "options": ["Piped", "Borewell", "Handpump", "Other"]},

    {"name": "Sanitation Facility", "type": "select", "notion_prop": "Sanitation Facility",
     "options": ["Private", "Shared", "None"]},

    {"name": "Primary Source of Income", "type": "select", "notion_prop": "Primary Source of Income",
     "options": ["Employment", "Business", "Agriculture", "Other"]},

    {"name": "Monthly Regular Income (₹)", "type": "number", "format": "float", "notion_prop": "Monthly Regular Income (₹)"},

    {"name": "Monthly Seasonal Income (₹)", "type": "number", "format": "float", "notion_prop": "Monthly Seasonal Income (₹)"},

    {"name": "Other Income (₹)", "type": "number", "format": "float", "notion_prop": "Other Income (₹)"},

    {"name": "Monthly Household Expenses (₹)", "type": "number", "format": "float", "notion_prop": "Monthly Household Expenses (₹)"},

    {"name": "Monthly Loan EMIs (₹)", "type": "number", "format": "float", "notion_prop": "Monthly Loan EMIs (₹)"},

    {"name": "Other Recurring Expenses (₹)", "type": "number", "format": "float", "notion_prop": "Other Recurring Expenses (₹)"},

    {"name": "Business Name", "type": "rich_text", "notion_prop": "Business Name"},

    {"name": "Business Type", "type": "select", "notion_prop": "Business Type",
     "options": ["Retail", "Services", "Manufacturing", "Agriculture", "Other"]},

    {"name": "Years in Operation", "type": "number", "format": "int", "notion_prop": "Years in Operation"},

    {"name": "Monthly Sales (₹)", "type": "number", "format": "float", "notion_prop": "Monthly Sales (₹)"},

    {"name": "Average Profit (₹)", "type": "number", "format": "float", "notion_prop": "Average Profit (₹)"},

    {"name": "Number of Employees", "type": "number", "format": "int", "notion_prop": "Number of Employees"},

    {"name": "Inventory / Stock Value (₹)", "type": "number", "format": "float", "notion_prop": "Inventory / Stock Value (₹)"},

    {"name": "Assets Observed", "type": "rich_text", "notion_prop": "Assets Observed"},

    {"name": "Livestock Owned", "type": "rich_text", "notion_prop": "Livestock Owned"},

    {"name": "Vehicles Owned", "type": "rich_text", "notion_prop": "Vehicles Owned"},

    {"name": "Agricultural Land (Acres)", "type": "number", "format": "float", "notion_prop": "Agricultural Land (Acres)"},

    {"name": "Other Assets", "type": "rich_text", "notion_prop": "Other Assets"},

    {"name": "Neighbours’ Feedback", "type": "rich_text", "notion_prop": "Neighbours’ Feedback"},

    {"name": "Past Relationship with MFI / Bank", "type": "rich_text", "notion_prop": "Past Relationship with MFI / Bank"},

    {"name": "Signs of Financial Stress", "type": "select", "notion_prop": "Signs of Financial Stress",
     "options": ["None", "Mild", "Severe"]},

    {"name": "Officer Recommendation", "type": "select", "notion_prop": "Officer Recommendation",
     "options": ["Approve", "Reject", "Hold"]},

    {"name": "Remarks", "type": "rich_text", "notion_prop": "Remarks"},

    {"name": "Photo URLs", "type": "url", "notion_prop": "Photo URLs"},

    {"name": "Officer ID", "type": "rich_text", "notion_prop": "Officer ID"},

    {"name": "Verification Logged in LMS", "type": "checkbox", "notion_prop": "Verification Logged in LMS",
     "inline_label": "I confirm the verification is logged in LMS"},

]
