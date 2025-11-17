"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name.

This project targets Dutch bookkeeping use cases (facturen, uitgaven, btw).
"""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from datetime import date

# Gebruikers kunnen later worden uitgebreid
class User(BaseModel):
    name: str = Field(..., description="Volledige naam")
    email: str = Field(..., description="E-mailadres")
    is_active: bool = Field(True, description="Actief")

class InvoiceItem(BaseModel):
    description: str = Field(..., description="Omschrijving")
    quantity: float = Field(1, ge=0, description="Aantal")
    unit_price: float = Field(..., ge=0, description="Prijs per eenheid (excl. btw)")
    vat_rate: float = Field(21, ge=0, le=100, description="BTW-percentage")

class Invoice(BaseModel):
    customer_name: str = Field(..., description="Klantnaam")
    customer_email: Optional[str] = Field(None, description="E-mail klant")
    issue_date: date = Field(..., description="Factuurdatum")
    due_date: Optional[date] = Field(None, description="Vervaldatum")
    status: Literal["concept", "verzonden", "betaald", "verlopen"] = Field("concept")
    items: List[InvoiceItem] = Field(default_factory=list)
    notes: Optional[str] = Field(None, description="Notities op factuur")

class Expense(BaseModel):
    vendor: str = Field(..., description="Leverancier/verkoper")
    expense_date: date = Field(..., description="Datum uitgave")
    amount_ex_vat: float = Field(..., ge=0, description="Bedrag excl. btw")
    vat_rate: float = Field(21, ge=0, le=100, description="BTW-percentage")
    category: Optional[str] = Field(None, description="Categorie (bijv. Software, Reizen)")
    note: Optional[str] = Field(None, description="Notitie")

class DashboardSummary(BaseModel):
    revenue_ex_vat: float
    revenue_vat: float
    revenue_inc_vat: float
    expenses_ex_vat: float
    expenses_vat: float
    expenses_inc_vat: float
    open_invoices: int
    paid_invoices: int
