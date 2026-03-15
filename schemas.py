from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, List
from datetime import date


class UserCreate(BaseModel):
    name: str
    email: str
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str


class LoginRequest(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class ExpenseCreate(BaseModel):
    category: str
    amount: float
    description: Optional[str] = None
    date: date


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    amount: float
    description: Optional[str] = None
    date: date


class Analytics(BaseModel):
    total_spent: float
    category_breakdown: Dict[str, float]
    monthly_totals: Dict[str, float]
    top_category: str
    expense_count: int


class BudgetCreate(BaseModel):
    category: str
    limit: float
    month: str


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    limit: float
    month: str


class BudgetStatus(BaseModel):
    category: str
    spent: float
    limit: float
    remaining: float
    percent_used: float
    status: str


class InsightResponse(BaseModel):
    summary: str
    tips: List[str]
    biggest_category: str


class EmailReportRequest(BaseModel):
    month: str