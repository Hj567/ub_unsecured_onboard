import os
from jinja2 import Template

# Path to template (make sure you've renamed to remove spaces)
file_path = os.path.join("Microfinancing_Loan_Agreement.html")

# Load template
with open(file_path, encoding="utf-8") as f:
    tpl = Template(f.read())

# Render with borrower/loan data
html = tpl.render({
    "Borrower_Name": "Aashman Rastogi",
    "Borrower_Address": "Connaught Place, New Delhi",
    "Borrower_Phone": "+91 9999999999",
    "Borrower_Guardian": "Mr. Rastogi",
    "Amount_Sanctioned": "₹5,00,000",
    "Amount_Sanctioned_Words": "Five Lakh Rupees Only",
    "date": "03",
    "month": "October",
    "year": "2025"
})

# Output file path (new file with replaced fields)
output_path = os.path.join("contracts", "Microfinancing_Loan_Agreement_Filled.html")

# Write the filled contract
with open(output_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"✅ Loan agreement generated: {output_path}")
