from sqlalchemy import create_engine, Column, Integer, String, Float, Date, ForeignKey, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
import datetime
import os


# ── Database URL ───────────────────────────────────────────────────────────────
# On Render: DATABASE_URL env var is set automatically by Render PostgreSQL addon
# Locally:   Falls back to SQLite so local development still works
DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL:
    # Render provides postgres:// but SQLAlchemy requires postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)
else:
    # Local development — use SQLite
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    SQLITE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'expenses.db')}"
    engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(Date, default=datetime.date.today)

    expenses = relationship(
        "ExpenseModel",
        back_populates="owner",
        cascade="all, delete"
    )

    budgets = relationship(
        "BudgetModel",
        back_populates="owner",
        cascade="all, delete"
    )


class ExpenseModel(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    date = Column(Date, default=datetime.date.today)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("UserModel", back_populates="expenses")


class BudgetModel(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False)
    limit = Column(Float, nullable=False)
    month = Column(String, nullable=False)  # format: YYYY-MM
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("UserModel", back_populates="budgets")


# Dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Create tables automatically
def create_tables():
    Base.metadata.create_all(bind=engine)