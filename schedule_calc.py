#!/usr/bin/env python3
import math
from datetime import date, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import pandas as pd

# =============== Core Schedule Logic ===============

def add_months(d: date, months: int) -> date:
    """Add 'months' to a date, clamping to last day of month if needed."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last_day = [31,
                29 if (y % 400 == 0 or (y % 4 == 0 and y % 100 != 0)) else 28,
                31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m-1]
    return date(y, m, min(d.day, last_day))

def annuity_payment(P: float, r: float, n: int) -> float:
    """EMI = P * r * (1+r)^n / ((1+r)^n - 1)"""
    if n <= 0:
        return 0.0
    if abs(r) < 1e-15:
        return P / n
    factor = (1 + r) ** n
    return P * r * factor / (factor - 1)

def to_money(x):
    return round(float(x), 2)

def schedule_monthly_emi(principal, annual_rate, start_date, years=0, months=0, leftover_days=0, basis=365):
    """
    MONTHLY (arrears): first EMI due = start_date + 1 month
    End date = start_date + total_months months + leftover_days days
    """
    total_months = int(years) * 12 + int(months)
    mr = annual_rate / 12.0
    dr = annual_rate / float(basis)

    rows = []
    opening = float(principal)
    emi = annuity_payment(opening, mr, total_months)

    # First due = start + 1 month (arrears)
    due = add_months(start_date, 1)

    for k in range(1, total_months + 1):
        interest = opening * mr
        principal_pay = emi - interest

        # If there is NO stub, close fully on the last monthly EMI
        if k == total_months and leftover_days == 0:
            principal_pay = opening
            emi_this = interest + principal_pay
        else:
            emi_this = emi

        closing = opening - principal_pay

        rows.append({
            "EMI DUE DATE": due,
            "OPENING OUTSTANDING": to_money(opening),
            "INTEREST": to_money(interest),
            "PRINCIPLE": to_money(principal_pay),   # keeping header text as requested
            "INSTALMENT": to_money(emi_this),
            "CLOSING PRINCIPLE": to_money(closing)
        })

        opening = closing
        due = add_months(due, 1)  # increment one calendar month

    # Stub period (daily interest, final payoff)
    if leftover_days and opening > 0.005:
        # Last monthly due is one month before 'due' now
        last_due = add_months(due, -1) if total_months > 0 else start_date
        stub_due = last_due + timedelta(days=leftover_days)  # end date = start + months + leftover_days
        stub_interest = opening * dr * leftover_days
        final_payment = opening + stub_interest
        rows.append({
            "EMI DUE DATE": stub_due,
            "OPENING OUTSTANDING": to_money(opening),
            "INTEREST": to_money(stub_interest),
            "PRINCIPLE": to_money(opening),
            "INSTALMENT": to_money(final_payment),
            "CLOSING PRINCIPLE": 0.00
        })

    df = pd.DataFrame(rows, columns=[
        "EMI DUE DATE", "OPENING OUTSTANDING", "INTEREST",
        "PRINCIPLE", "INSTALMENT", "CLOSING PRINCIPLE"
    ])
    return df

def schedule_daily_emi(principal, annual_rate, start_date, days, basis=365):
    """
    DAILY (arrears): first EMI due = start_date + 1 day
    End date = start_date + days
    """
    n = int(days)
    dr = annual_rate / float(basis)
    emi = annuity_payment(principal, dr, n)

    rows = []
    opening = float(principal)

    for d in range(1, n + 1):
        interest = opening * dr
        principal_pay = emi - interest

        # Close exactly on last day
        if d == n:
            principal_pay = opening
            emi_this = interest + principal_pay
        else:
            emi_this = emi

        closing = opening - principal_pay

        rows.append({
            "EMI DUE DATE": start_date + timedelta(days=d),  # first = +1 day, last = +n days
            "OPENING OUTSTANDING": to_money(opening),
            "INTEREST": to_money(interest),
            "PRINCIPLE": to_money(principal_pay),
            "INSTALMENT": to_money(emi_this),
            "CLOSING PRINCIPLE": to_money(closing)
        })

        opening = closing

    df = pd.DataFrame(rows, columns=[
        "EMI DUE DATE", "OPENING OUTSTANDING", "INTEREST",
        "PRINCIPLE", "INSTALMENT", "CLOSING PRINCIPLE"
    ])
    return df

# ============================== GUI Application ===============================

class EMIGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EMI Schedule → Excel")
        self.geometry("980x640")
        self.minsize(960, 620)

        self._build_form()
        self._build_preview()

    def _build_form(self):
        frm = ttk.Frame(self, padding=12)
        frm.pack(side=tk.TOP, fill=tk.X)

        # Row 1: Principal, Annual Rate (%), Basis
        ttk.Label(frm, text="Principal (e.g., 25000000):").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.var_principal = tk.StringVar(value="25000000")
        ttk.Entry(frm, textvariable=self.var_principal, width=20).grid(row=0, column=1, sticky="w", padx=4, pady=4)

        ttk.Label(frm, text="Annual Rate (%):").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        self.var_rate = tk.StringVar(value="9")
        ttk.Entry(frm, textvariable=self.var_rate, width=20).grid(row=0, column=3, sticky="w", padx=4, pady=4)

        ttk.Label(frm, text="Day-Count Basis:").grid(row=0, column=4, sticky="w", padx=4, pady=4)
        self.var_basis = tk.StringVar(value="365")
        ttk.Combobox(frm, textvariable=self.var_basis, values=["365", "360"], width=6, state="readonly").grid(row=0, column=5, sticky="w", padx=4, pady=4)

        # Row 2: Start Date
        ttk.Label(frm, text="Start Date (YYYY-MM-DD):").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.var_start = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(frm, textvariable=self.var_start, width=20).grid(row=1, column=1, sticky="w", padx=4, pady=4)

        # Row 3: Mode radio
        self.var_mode = tk.StringVar(value="monthly")
        ttk.Label(frm, text="Mode:").grid(row=1, column=2, sticky="w", padx=4, pady=4)
        ttk.Radiobutton(frm, text="Monthly EMI", variable=self.var_mode, value="monthly", command=self._toggle_mode).grid(row=1, column=3, sticky="w", padx=4, pady=4)
        ttk.Radiobutton(frm, text="Daily EMI", variable=self.var_mode, value="daily", command=self._toggle_mode).grid(row=1, column=4, sticky="w", padx=4, pady=4)

        # Row 4: Tenor (Monthly mode)
        self.tenor_monthly_frame = ttk.Frame(frm)
        self.tenor_monthly_frame.grid(row=2, column=0, columnspan=6, sticky="w", padx=4, pady=4)

        ttk.Label(self.tenor_monthly_frame, text="Years:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.var_years = tk.StringVar(value="0")
        ttk.Entry(self.tenor_monthly_frame, textvariable=self.var_years, width=8).grid(row=0, column=1, sticky="w", padx=4, pady=4)

        ttk.Label(self.tenor_monthly_frame, text="Months:").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        self.var_months = tk.StringVar(value="4")
        ttk.Entry(self.tenor_monthly_frame, textvariable=self.var_months, width=8).grid(row=0, column=3, sticky="w", padx=4, pady=4)

        ttk.Label(self.tenor_monthly_frame, text="Leftover Stub Days:").grid(row=0, column=4, sticky="w", padx=4, pady=4)
        self.var_stub = tk.StringVar(value="15")
        ttk.Entry(self.tenor_monthly_frame, textvariable=self.var_stub, width=8).grid(row=0, column=5, sticky="w", padx=4, pady=4)

        # Row 5: Tenor (Daily mode)
        self.tenor_daily_frame = ttk.Frame(frm)
        self.tenor_daily_frame.grid(row=3, column=0, columnspan=6, sticky="w", padx=4, pady=4)

        ttk.Label(self.tenor_daily_frame, text="Days:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.var_days = tk.StringVar(value="135")
        ttk.Entry(self.tenor_daily_frame, textvariable=self.var_days, width=10).grid(row=0, column=1, sticky="w", padx=4, pady=4)

        # Buttons
        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=4, column=0, columnspan=6, sticky="w", padx=4, pady=10)

        ttk.Button(btn_frame, text="Generate (Preview)", command=self.generate_preview).grid(row=0, column=0, padx=4)
        ttk.Button(btn_frame, text="Generate & Save Excel", command=self.generate_and_save).grid(row=0, column=1, padx=8)

        self._toggle_mode()

    def _build_preview(self):
        # Preview table (all rows; scrollable)
        wrapper = ttk.Frame(self, padding=(12, 0, 12, 12))
        wrapper.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        cols = ["EMI DUE DATE", "OPENING OUTSTANDING", "INTEREST", "PRINCIPLE", "INSTALMENT", "CLOSING PRINCIPLE"]
        self.tree = ttk.Treeview(wrapper, columns=cols, show="headings", height=18)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=160, anchor="center")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vsb = ttk.Scrollbar(wrapper, orient="vertical", command=self.tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)

        # Status bar
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status, anchor="w", padding=(12, 4)).pack(side=tk.BOTTOM, fill=tk.X)

    def _toggle_mode(self):
        mode = self.var_mode.get()
        if mode == "monthly":
            self.tenor_monthly_frame.grid()
            self.tenor_daily_frame.grid_remove()
        else:
            self.tenor_daily_frame.grid()
            self.tenor_monthly_frame.grid_remove()

    def _read_inputs(self):
        try:
            principal = float(self.var_principal.get())
            rate_pct = float(self.var_rate.get())
            rate = rate_pct / 100.0
            basis = int(self.var_basis.get())
            y, m, d = map(int, self.var_start.get().split("-"))
            start = date(y, m, d)
        except Exception as e:
            messagebox.showerror("Input Error", f"Please check Principal, Rate, Basis, and Start Date.\n\n{e}")
            return None

        mode = self.var_mode.get()
        if mode == "monthly":
            try:
                years = int(self.var_years.get())
                months = int(self.var_months.get())
                stub = int(self.var_stub.get())
            except Exception as e:
                messagebox.showerror("Input Error", f"Please check Years/Months/Stub.\n\n{e}")
                return None
            return dict(mode=mode, principal=principal, rate=rate, basis=basis, start=start,
                        years=years, months=months, stub=stub)
        else:
            try:
                days = int(self.var_days.get())
            except Exception as e:
                messagebox.showerror("Input Error", f"Please check Days.\n\n{e}")
                return None
            return dict(mode=mode, principal=principal, rate=rate, basis=basis, start=start,
                        days=days)

    def _build_df(self, params):
        if params["mode"] == "monthly":
            return schedule_monthly_emi(
                principal=params["principal"],
                annual_rate=params["rate"],
                start_date=params["start"],
                years=params["years"],
                months=params["months"],
                leftover_days=params["stub"],
                basis=params["basis"]
            )
        else:
            return schedule_daily_emi(
                principal=params["principal"],
                annual_rate=params["rate"],
                start_date=params["start"],
                days=params["days"],
                basis=params["basis"]
            )

    def generate_preview(self):
        params = self._read_inputs()
        if not params:
            return
        df = self._build_df(params)
        self._fill_tree(df)
        self.status.set(f"Preview generated. Rows: {len(df)}")

    def generate_and_save(self):
        params = self._read_inputs()
        if not params:
            return
        df = self._build_df(params)

        path = filedialog.asksaveasfilename(
            title="Save Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel Workbook", "*.xlsx")],
            initialfile="loan_schedule.xlsx"
        )
        if not path:
            return
        try:
            with pd.ExcelWriter(path, engine="openpyxl") as xl:
                df.to_excel(xl, index=False, sheet_name="Schedule")
                ws = xl.sheets["Schedule"]
                for col in range(1, ws.max_column + 1):
                    cell = ws.cell(row=1, column=col)
                    cell.font = cell.font.copy(bold=True)
                    ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = 22
            self.status.set(f"Saved: {path}")
            messagebox.showinfo("Success", f"Schedule saved to:\n{path}")
            self._fill_tree(df)
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save Excel:\n{e}")

    def _fill_tree(self, df: pd.DataFrame):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for _, r in df.iterrows():
            vals = [str(r[c]) for c in df.columns]
            self.tree.insert("", "end", values=vals)

if __name__ == "__main__":
    app = EMIGUI()
    app.mainloop()
