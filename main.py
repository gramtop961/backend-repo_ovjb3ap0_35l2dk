import os
from datetime import datetime, date, timedelta
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import List, Dict, Any, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext

from database import db, create_document, get_documents
from schemas import Invoice, Expense, DashboardSummary, UserCreate, UserLogin, UserOut, Token

# ---------------- App & Security Setup ----------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 uur

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
http_bearer = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer)) -> Optional[dict]:
    if credentials is None:
        return None
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
        users = get_documents("user", {"email": email}, limit=1)
        return users[0] if users else None
    except JWTError:
        return None


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

# ---------------- Auth endpoints ----------------
@app.post("/auth/signup", response_model=UserOut)
def signup(user: UserCreate):
    try:
        existing = get_documents("user", {"email": user.email}, limit=1)
        if existing:
            raise HTTPException(status_code=400, detail="E-mailadres is al geregistreerd")
        doc = {
            "name": user.name,
            "email": user.email,
            "hashed_password": get_password_hash(user.password),
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        create_document("user", doc)
        return UserOut(name=user.name, email=user.email)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/login", response_model=Token)
def login(payload: UserLogin):
    try:
        users = get_documents("user", {"email": payload.email}, limit=1)
        if not users:
            raise HTTPException(status_code=400, detail="Onjuiste inloggegevens")
        user = users[0]
        if not verify_password(payload.password, user.get("hashed_password", "")):
            raise HTTPException(status_code=400, detail="Onjuiste inloggegevens")
        token = create_access_token({"sub": user["email"]})
        return {"access_token": token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auth/me", response_model=UserOut)
def me(current_user: dict = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Niet geautoriseerd")
    return {"name": current_user.get("name"), "email": current_user.get("email")}


# ---------------- Dashboard endpoints ----------------
@app.get("/api/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary():
    try:
        invoices = get_documents("invoice")
        revenue_ex_vat = 0.0
        revenue_vat = 0.0
        paid_invoices = 0
        open_invoices = 0
        for inv in invoices:
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


# ---------------- CRUD/listing endpoints ----------------
@app.get("/api/invoices")
def list_invoices(limit: int = Query(20, ge=1, le=200)) -> List[Dict[str, Any]]:
    try:
        items = get_documents("invoice")
        def sort_key(x):
            ca = x.get("created_at")
            idate = x.get("issue_date")
            return (str(ca or ""), str(idate or ""))
        items.sort(key=sort_key, reverse=True)
        return items[:limit]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/expenses")
def list_expenses(limit: int = Query(20, ge=1, le=200)) -> List[Dict[str, Any]]:
    try:
        items = get_documents("expense")
        def sort_key(x):
            ca = x.get("created_at")
            edate = x.get("expense_date")
            return (str(ca or ""), str(edate or ""))
        items.sort(key=sort_key, reverse=True)
        return items[:limit]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- Reports endpoints ----------------
@app.get("/api/reports/monthly")
def monthly_report(year: int = Query(datetime.utcnow().year)):
    try:
        months = {m: {
            "revenue_ex_vat": 0.0,
            "revenue_vat": 0.0,
            "revenue_inc_vat": 0.0,
            "expenses_ex_vat": 0.0,
            "expenses_vat": 0.0,
            "expenses_inc_vat": 0.0
        } for m in range(1,13)}

        invoices = get_documents("invoice")
        for inv in invoices:
            try:
                d = inv.get("issue_date")
                if isinstance(d, str):
                    d = date.fromisoformat(d)
                if not isinstance(d, date):
                    continue
                if d.year != year:
                    continue
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
                m = d.month
                months[m]["revenue_ex_vat"] += inv_ex
                months[m]["revenue_vat"] += inv_vat
                months[m]["revenue_inc_vat"] += inv_ex + inv_vat
            except Exception:
                continue

        expenses = get_documents("expense")
        for ex in expenses:
            try:
                d = ex.get("expense_date")
                if isinstance(d, str):
                    d = date.fromisoformat(d)
                if not isinstance(d, date):
                    continue
                if d.year != year:
                    continue
                amount_ex = float(ex.get("amount_ex_vat", 0))
                rate = float(ex.get("vat_rate", 21))
                m = d.month
                months[m]["expenses_ex_vat"] += amount_ex
                months[m]["expenses_vat"] += amount_ex * (rate/100)
                months[m]["expenses_inc_vat"] += amount_ex + (amount_ex * (rate/100))
            except Exception:
                continue

        result = []
        for m in range(1,13):
            entry = {"month": m}
            entry.update({k: round(v, 2) for k, v in months[m].items()})
            result.append(entry)
        return {"year": year, "months": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- Create endpoints ----------------
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
