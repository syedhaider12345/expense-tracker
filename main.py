from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks, status, Header
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
from config import ADMIN_EMAIL, ADMIN_PASSWORD


app = FastAPI(
    title="Personal Expense Tracker",
    description="Track, analyze, and get AI-powered insights on your expenses.",
    version="4.0.0",
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


@app.get("/admin", include_in_schema=False)
def serve_admin():
    return FileResponse("static/admin.html")


# ── Helper: PostgreSQL-safe month filtering ───────────────────────────────────
# FIX: Replaced func.strftime (SQLite only) with date range (works on PostgreSQL too)

def month_date_range(month_str: str):
    """Convert 'YYYY-MM' to (start_date, end_date) for database filtering."""
    try:
        year, mon = map(int, month_str.split('-'))
        start = datetime.date(year, mon, 1)
        if mon == 12:
            end = datetime.date(year + 1, 1, 1)
        else:
            end = datetime.date(year, mon + 1, 1)
        return start, end
    except Exception:
        today = datetime.date.today()
        start = today.replace(day=1)
        if today.month == 12:
            end = datetime.date(today.year + 1, 1, 1)
        else:
            end = today.replace(month=today.month + 1, day=1)
        return start, end


def filter_by_month(query, model, month_str: str):
    """Apply month filter to a SQLAlchemy query using date range."""
    start, end = month_date_range(month_str)
    return query.filter(model.date >= start, model.date < end)


# ── Admin Auth ────────────────────────────────────────────────────────────────

def get_admin_user(authorization: str = Header(None)):
    """Verify admin token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin authentication required")
    token = authorization.replace("Bearer ", "")
    # Admin token is simply "admin:{ADMIN_PASSWORD}" base64 encoded — lightweight
    import base64
    try:
        decoded = base64.b64decode(token).decode()
        email, password = decoded.split(":", 1)
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            return {"email": email, "role": "admin"}
    except Exception:
        pass
    raise HTTPException(status_code=403, detail="Invalid admin credentials")


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


@app.post("/auth/admin-login", tags=["Auth"])
def admin_login(credentials: LoginRequest):
    """Admin login — returns a base64 token for admin dashboard."""
    if credentials.email != ADMIN_EMAIL or credentials.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    import base64
    token = base64.b64encode(f"{credentials.email}:{credentials.password}".encode()).decode()
    return {"access_token": token, "token_type": "admin"}


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
    start, end = month_date_range(month)

    for budget in budgets:
        spent = db.query(func.sum(ExpenseModel.amount)).filter(
            ExpenseModel.user_id == current_user.id,
            ExpenseModel.category == budget.category,
            ExpenseModel.date >= start,
            ExpenseModel.date < end
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
                limit=budget.limit,
                spent=spent,
                remaining=round(budget.limit - spent, 2),
                percent_used=percent_used,
                status=status_val
            )
        )

    return results


# ── AI Insights ───────────────────────────────────────────────────────────────

@app.get("/ai/insights", response_model=InsightResponse, tags=["AI"])
def get_ai_insights(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    month = datetime.date.today().strftime("%Y-%m")
    start, end = month_date_range(month)

    # FIX: Use date range instead of strftime (PostgreSQL compatible)
    expenses = db.query(ExpenseModel).filter(
        ExpenseModel.user_id == current_user.id,
        ExpenseModel.date >= start,
        ExpenseModel.date < end
    ).all()

    category_breakdown = defaultdict(float)
    for e in expenses:
        category_breakdown[e.category] += e.amount
    category_breakdown = {k: round(v, 2) for k, v in category_breakdown.items()}
    total_spent = round(sum(category_breakdown.values()), 2)

    budgets = db.query(BudgetModel).filter(
        BudgetModel.user_id == current_user.id,
        BudgetModel.month == month
    ).all()

    budget_statuses = []
    for budget in budgets:
        spent = db.query(func.sum(ExpenseModel.amount)).filter(
            ExpenseModel.user_id == current_user.id,
            ExpenseModel.category == budget.category,
            ExpenseModel.date >= start,
            ExpenseModel.date < end
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

@app.post("/email/send-report", tags=["Email"])
def send_email_report(
    request: EmailReportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    month = request.month
    start, end = month_date_range(month)

    # FIX: Use date range instead of strftime (PostgreSQL compatible)
    expenses = db.query(ExpenseModel).filter(
        ExpenseModel.user_id == current_user.id,
        ExpenseModel.date >= start,
        ExpenseModel.date < end
    ).all()

    if not expenses:
        raise HTTPException(
            status_code=400,
            detail=f"No expenses found for {month}. Add some expenses first."
        )

    category_breakdown = defaultdict(float)
    for e in expenses:
        category_breakdown[e.category] += e.amount
    category_breakdown = {k: round(v, 2) for k, v in category_breakdown.items()}
    total_spent = round(sum(category_breakdown.values()), 2)

    budgets = db.query(BudgetModel).filter(
        BudgetModel.user_id == current_user.id,
        BudgetModel.month == month
    ).all()

    budget_statuses = []
    for budget in budgets:
        spent = db.query(func.sum(ExpenseModel.amount)).filter(
            ExpenseModel.user_id == current_user.id,
            ExpenseModel.category == budget.category,
            ExpenseModel.date >= start,
            ExpenseModel.date < end
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

    try:
        month_display = datetime.datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    except ValueError:
        month_display = month

    ai_insights = generate_spending_insights(
        user_name=current_user.name,
        month=month_display,
        category_breakdown=category_breakdown,
        monthly_total=total_spent,
        budget_statuses=budget_statuses
    )
    ai_summary = ai_insights.get("summary", "")

    background_tasks.add_task(
        send_monthly_report,
        current_user.email,
        current_user.name,
        month_display,
        total_spent,
        category_breakdown,
        budget_statuses,
        ai_summary
    )

    return {"message": f"Email report is being sent to {current_user.email}"}


# ── Admin Endpoints ───────────────────────────────────────────────────────────

@app.get("/admin/stats", tags=["Admin"])
def admin_stats(
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user)
):
    """Platform-wide statistics for the admin dashboard."""
    total_users = db.query(func.count(UserModel.id)).scalar() or 0
    total_expenses = db.query(func.count(ExpenseModel.id)).scalar() or 0
    total_amount = db.query(func.sum(ExpenseModel.amount)).scalar() or 0

    # This month stats
    month = datetime.date.today().strftime("%Y-%m")
    start, end = month_date_range(month)
    month_expenses = db.query(func.count(ExpenseModel.id)).filter(
        ExpenseModel.date >= start, ExpenseModel.date < end
    ).scalar() or 0
    month_amount = db.query(func.sum(ExpenseModel.amount)).filter(
        ExpenseModel.date >= start, ExpenseModel.date < end
    ).scalar() or 0

    return {
        "total_users": total_users,
        "total_expenses": total_expenses,
        "total_amount": round(float(total_amount), 2),
        "month_expenses": month_expenses,
        "month_amount": round(float(month_amount), 2)
    }


@app.get("/admin/users", tags=["Admin"])
def admin_get_users(
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user)
):
    """Get all users with their expense stats."""
    users = db.query(UserModel).order_by(UserModel.created_at.desc()).all()
    result = []
    for user in users:
        expense_count = db.query(func.count(ExpenseModel.id)).filter(
            ExpenseModel.user_id == user.id
        ).scalar() or 0
        total_spent = db.query(func.sum(ExpenseModel.amount)).filter(
            ExpenseModel.user_id == user.id
        ).scalar() or 0

        # Last activity
        last_expense = db.query(ExpenseModel).filter(
            ExpenseModel.user_id == user.id
        ).order_by(ExpenseModel.date.desc()).first()

        result.append({
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "joined": str(user.created_at),
            "expense_count": expense_count,
            "total_spent": round(float(total_spent), 2),
            "last_activity": str(last_expense.date) if last_expense else "No activity"
        })
    return result


@app.get("/admin/recent-activity", tags=["Admin"])
def admin_recent_activity(
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user)
):
    """Get recent expenses across all users."""
    expenses = db.query(ExpenseModel).order_by(
        ExpenseModel.date.desc(), ExpenseModel.id.desc()
    ).limit(20).all()

    result = []
    for e in expenses:
        user = db.query(UserModel).filter(UserModel.id == e.user_id).first()
        result.append({
            "id": e.id,
            "user_name": user.name if user else "Unknown",
            "user_email": user.email if user else "Unknown",
            "category": e.category,
            "amount": e.amount,
            "description": e.description or "",
            "date": str(e.date)
        })
    return result


@app.post("/admin/send-message", tags=["Admin"])
def admin_send_message(
    request: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user)
):
    """Send a custom message email to one user or all users."""
    target = request.get("target", "all")   # "all" or a specific user email
    subject = request.get("subject", "Message from Expense Tracker")
    message = request.get("message", "")

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if target == "all":
        users = db.query(UserModel).filter(UserModel.is_active == True).all()
    else:
        user = db.query(UserModel).filter(UserModel.email == target).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        users = [user]

    from email_service import send_custom_message
    for user in users:
        background_tasks.add_task(send_custom_message, user.email, user.name, subject, message)

    return {"message": f"Message queued for {len(users)} user(s)"}


@app.delete("/admin/users/{user_id}", tags=["Admin"])
def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user)
):
    """Delete a user and all their data."""
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"message": f"User {user.email} deleted"}