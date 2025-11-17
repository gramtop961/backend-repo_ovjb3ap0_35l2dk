import os
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from database import db, create_document, get_documents
from schemas import Invoice, Expense, DashboardSummary

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "BGAI.nl API draait"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected & Working"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
            response["connection_status"] = "Connected"
            collections = db.list_collection_names()
            response["collections"] = collections[:10]
        else:
            response["database"] = "⚠️ Not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

# ---------------- Dashboard endpoints ----------------
@app.get("/api/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary():
    try:
        # Aggregate invoices
        invoices = get_documents("invoice")
        revenue_ex_vat = 0.0
        revenue_vat = 0.0
        paid_invoices = 0
        open_invoices = 0
        for inv in invoices:
            # Sum line items
            inv_ex = 0.0
            inv_vat = 0.0
            for it in inv.get("items", []):
                qty = float(it.get("quantity", 0))
                unit = float(it.get("unit_price", 0))
                rate = float(it.get("vat_rate", 21))
                line_ex = qty * unit
                line_vat = line_ex * (rate/100)
                inv_ex += line_ex
                inv_vat += line_vat
            revenue_ex_vat += inv_ex
            revenue_vat += inv_vat
            if inv.get("status") == "betaald":
                paid_invoices += 1
            else:
                open_invoices += 1
        # Aggregate expenses
        expenses = get_documents("expense")
        expenses_ex_vat = 0.0
        expenses_vat = 0.0
        for ex in expenses:
            amount_ex = float(ex.get("amount_ex_vat", 0))
            rate = float(ex.get("vat_rate", 21))
            expenses_ex_vat += amount_ex
            expenses_vat += amount_ex * (rate/100)

        return DashboardSummary(
            revenue_ex_vat=round(revenue_ex_vat, 2),
            revenue_vat=round(revenue_vat, 2),
            revenue_inc_vat=round(revenue_ex_vat + revenue_vat, 2),
            expenses_ex_vat=round(expenses_ex_vat, 2),
            expenses_vat=round(expenses_vat, 2),
            expenses_inc_vat=round(expenses_ex_vat + expenses_vat, 2),
            open_invoices=open_invoices,
            paid_invoices=paid_invoices,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------- Minimal create endpoints to seed data ----------------
@app.post("/api/invoices")
def create_invoice(invoice: Invoice):
    try:
        invoice_dict = invoice.model_dump()
        invoice_dict["created_at"] = datetime.utcnow()
        invoice_dict["updated_at"] = datetime.utcnow()
        new_id = create_document("invoice", invoice_dict)
        return {"id": new_id, "status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/expenses")
def create_expense(expense: Expense):
    try:
        expense_dict = expense.model_dump()
        expense_dict["created_at"] = datetime.utcnow()
        expense_dict["updated_at"] = datetime.utcnow()
        new_id = create_document("expense", expense_dict)
        return {"id": new_id, "status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
