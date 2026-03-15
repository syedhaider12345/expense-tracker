from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
import datetime
from collections import defaultdict
import os

from database import get_db, create_tables, ExpenseModel, UserModel, BudgetModel
from schemas import (
    ExpenseCreate, ExpenseResponse, Analytics,
    UserCreate, UserResponse, Token, LoginRequest,
    BudgetCreate, BudgetResponse, BudgetStatus,
    InsightResponse, EmailReportRequest
)
from auth import hash_password, verify_password, create_access_token, get_current_user
from ai_service import generate_spending_insights
from email_service import send_monthly_report


app = FastAPI(
    title="Personal Expense Tracker",
    description="Track, analyze, and get AI-powered insights on your expenses.",
    version="3.0.0",
    docs_url="/docs"
)


@app.on_event("startup")
def startup():
    create_tables()


if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
def serve_ui():
    return FileResponse("static/index.html")


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/auth/register", response_model=Token, status_code=201, tags=["Auth"])
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    if db.query(UserModel).filter(UserModel.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = hash_password(user_data.password[:72])

    user = UserModel(
        name=user_data.name,
        email=user_data.email,
        hashed_password=hashed_password
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(data={"sub": str(user.id)})

    return Token(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )


@app.post("/auth/login", response_model=Token, tags=["Auth"])
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.email == credentials.email).first()

    if not user or not verify_password(credentials.password[:72], user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    token = create_access_token(data={"sub": str(user.id)})

    return Token(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )


@app.get("/auth/me", response_model=UserResponse, tags=["Auth"])
def get_me(current_user: UserModel = Depends(get_current_user)):
    return current_user


# ── Expenses ──────────────────────────────────────────────────────────────────

@app.post("/expenses", response_model=ExpenseResponse, status_code=201, tags=["Expenses"])
def add_expense(
    expense: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    record = ExpenseModel(**expense.model_dump(), user_id=current_user.id)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.get("/expenses", response_model=List[ExpenseResponse], tags=["Expenses"])
def get_expenses(
    category: Optional[str] = Query(None),
    start_date: Optional[datetime.date] = Query(None),
    end_date: Optional[datetime.date] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    q = db.query(ExpenseModel).filter(ExpenseModel.user_id == current_user.id)

    if category:
        q = q.filter(func.lower(ExpenseModel.category) == category.lower())
    if start_date:
        q = q.filter(ExpenseModel.date >= start_date)
    if end_date:
        q = q.filter(ExpenseModel.date <= end_date)

    return q.order_by(ExpenseModel.date.desc()).all()


@app.delete("/expenses/{expense_id}", status_code=204, tags=["Expenses"])
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    record = db.query(ExpenseModel).filter(
        ExpenseModel.id == expense_id,
        ExpenseModel.user_id == current_user.id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="Expense not found")

    db.delete(record)
    db.commit()


@app.get("/categories", response_model=List[str], tags=["Expenses"])
def get_categories(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    rows = db.query(ExpenseModel.category).filter(
        ExpenseModel.user_id == current_user.id
    ).distinct().all()
    return [r[0] for r in rows]


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.get("/analytics", response_model=Analytics, tags=["Analytics"])
def get_analytics(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    expenses = db.query(ExpenseModel).filter(
        ExpenseModel.user_id == current_user.id
    ).all()

    if not expenses:
        return Analytics(
            total_spent=0,
            category_breakdown={},
            monthly_totals={},
            top_category="N/A",
            expense_count=0
        )

    total = round(sum(e.amount for e in expenses), 2)

    cat_sums = defaultdict(float)
    month_sums = defaultdict(float)

    for e in expenses:
        cat_sums[e.category] += e.amount
        month_sums[e.date.strftime("%Y-%m")] += e.amount

    return Analytics(
        total_spent=total,
        category_breakdown={k: round(v, 2) for k, v in cat_sums.items()},
        monthly_totals={k: round(v, 2) for k, v in sorted(month_sums.items())},
        top_category=max(cat_sums, key=cat_sums.get),
        expense_count=len(expenses)
    )


# ── Budgets ───────────────────────────────────────────────────────────────────

@app.post("/budgets", response_model=BudgetResponse, tags=["Budgets"])
def create_budget(
    budget: BudgetCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    record = BudgetModel(
        category=budget.category,
        limit=budget.limit,
        month=budget.month,
        user_id=current_user.id
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.get("/budgets", response_model=List[BudgetResponse], tags=["Budgets"])
def get_budgets(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    return db.query(BudgetModel).filter(
        BudgetModel.user_id == current_user.id
    ).all()


@app.delete("/budgets/{budget_id}", status_code=204, tags=["Budgets"])
def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    record = db.query(BudgetModel).filter(
        BudgetModel.id == budget_id,
        BudgetModel.user_id == current_user.id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="Budget not found")

    db.delete(record)
    db.commit()


@app.get("/budgets/status", response_model=List[BudgetStatus], tags=["Budgets"])
def get_budget_status(
    month: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    budgets = db.query(BudgetModel).filter(
        BudgetModel.user_id == current_user.id,
        BudgetModel.month == month
    ).all()

    results = []

    for budget in budgets:
        spent = db.query(func.sum(ExpenseModel.amount)).filter(
            ExpenseModel.user_id == current_user.id,
            ExpenseModel.category == budget.category,
            func.strftime("%Y-%m", ExpenseModel.date) == month
        ).scalar() or 0

        spent = round(float(spent), 2)
        percent_used = round((spent / budget.limit * 100) if budget.limit else 0, 1)

        if percent_used < 80:
            status_val = "safe"
        elif percent_used < 100:
            status_val = "warning"
        else:
            status_val = "exceeded"

        results.append(
            BudgetStatus(
                category=budget.category,
                limit=budget.limit,             # FIX: was budget=budget.limit
                spent=spent,
                remaining=round(budget.limit - spent, 2),
                percent_used=percent_used,      # FIX: added missing field
                status=status_val               # FIX: added missing field
            )
        )

    return results


# ── AI Insights ───────────────────────────────────────────────────────────────

# FIX: This entire endpoint was missing from the original code
@app.get("/ai/insights", response_model=InsightResponse, tags=["AI"])
def get_ai_insights(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    month = datetime.date.today().strftime("%Y-%m")

    # Collect this month's expenses
    expenses = db.query(ExpenseModel).filter(
        ExpenseModel.user_id == current_user.id,
        func.strftime("%Y-%m", ExpenseModel.date) == month
    ).all()

    # Build category breakdown
    category_breakdown = defaultdict(float)
    for e in expenses:
        category_breakdown[e.category] += e.amount
    category_breakdown = {k: round(v, 2) for k, v in category_breakdown.items()}
    total_spent = round(sum(category_breakdown.values()), 2)

    # Build budget statuses for context
    budgets = db.query(BudgetModel).filter(
        BudgetModel.user_id == current_user.id,
        BudgetModel.month == month
    ).all()

    budget_statuses = []
    for budget in budgets:
        spent = db.query(func.sum(ExpenseModel.amount)).filter(
            ExpenseModel.user_id == current_user.id,
            ExpenseModel.category == budget.category,
            func.strftime("%Y-%m", ExpenseModel.date) == month
        ).scalar() or 0
        spent = round(float(spent), 2)
        percent = round((spent / budget.limit * 100) if budget.limit else 0, 1)
        status_val = "safe" if percent < 80 else ("warning" if percent < 100 else "exceeded")
        budget_statuses.append({
            "category": budget.category,
            "spent": spent,
            "limit": budget.limit,
            "percent_used": percent,
            "status": status_val
        })

    month_display = datetime.date.today().strftime("%B %Y")

    insights = generate_spending_insights(
        user_name=current_user.name,
        month=month_display,
        category_breakdown=category_breakdown,
        monthly_total=total_spent,
        budget_statuses=budget_statuses
    )

    return InsightResponse(
        summary=insights.get("summary", ""),
        tips=insights.get("tips", []),
        biggest_category=insights.get("biggest_category", "N/A")
    )


# ── Email Report ──────────────────────────────────────────────────────────────

# FIX: Completely rewritten — was calling send_monthly_report with wrong args,
#      and the schema expected {email} but frontend sends {month}
@app.post("/email/send-report", tags=["Email"])
def send_email_report(
    request: EmailReportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    month = request.month  # e.g. "2026-03"

    # Collect expenses for the requested month
    expenses = db.query(ExpenseModel).filter(
        ExpenseModel.user_id == current_user.id,
        func.strftime("%Y-%m", ExpenseModel.date) == month
    ).all()

    if not expenses:
        raise HTTPException(
            status_code=400,
            detail=f"No expenses found for {month}. Add some expenses first."
        )

    # Build category breakdown and total
    category_breakdown = defaultdict(float)
    for e in expenses:
        category_breakdown[e.category] += e.amount
    category_breakdown = {k: round(v, 2) for k, v in category_breakdown.items()}
    total_spent = round(sum(category_breakdown.values()), 2)

    # Build budget statuses for the month
    budgets = db.query(BudgetModel).filter(
        BudgetModel.user_id == current_user.id,
        BudgetModel.month == month
    ).all()

    budget_statuses = []
    for budget in budgets:
        spent = db.query(func.sum(ExpenseModel.amount)).filter(
            ExpenseModel.user_id == current_user.id,
            ExpenseModel.category == budget.category,
            func.strftime("%Y-%m", ExpenseModel.date) == month
        ).scalar() or 0
        spent = round(float(spent), 2)
        percent = round((spent / budget.limit * 100) if budget.limit else 0, 1)
        status_val = "safe" if percent < 80 else ("warning" if percent < 100 else "exceeded")
        budget_statuses.append({
            "category": budget.category,
            "spent": spent,
            "limit": budget.limit,
            "percent_used": percent,
            "status": status_val
        })

    # Format month as human-readable string for the email
    try:
        month_display = datetime.datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    except ValueError:
        month_display = month

    # Get a short AI summary to include in the email (falls back gracefully if no API key)
    ai_insights = generate_spending_insights(
        user_name=current_user.name,
        month=month_display,
        category_breakdown=category_breakdown,
        monthly_total=total_spent,
        budget_statuses=budget_statuses
    )
    ai_summary = ai_insights.get("summary", "")

    # Queue the email as a background task with all required arguments
    background_tasks.add_task(
        send_monthly_report,
        current_user.email,   # to_email
        current_user.name,    # user_name
        month_display,        # month (human-readable)
        total_spent,          # total_spent
        category_breakdown,   # category_breakdown dict
        budget_statuses,      # budget_statuses list of dicts
        ai_summary            # ai_summary string
    )

    return {"message": f"Email report is being sent to {current_user.email}"}