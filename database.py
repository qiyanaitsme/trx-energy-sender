import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Index, text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import config


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tron_address: Mapped[str | None] = mapped_column(String(34), nullable=True)
    energy_balance: Mapped[int] = mapped_column(Integer, default=0)
    balance_rub: Mapped[float] = mapped_column(Float, default=0.0)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    banned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ban_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    banned_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    total_deposited: Mapped[float] = mapped_column(Float, default=0.0)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_status_return", "status", "return_time"),
        Index("ix_transactions_user_status", "telegram_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    transaction_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    delegate_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    undelegate_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    amount_energy: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_trx: Mapped[float] = mapped_column(Float, nullable=False)
    recipient_address: Mapped[str] = mapped_column(String(34), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    payment_method: Mapped[str] = mapped_column(String(20), default="lolz")
    lolz_invoice_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delegated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    return_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_energy_returned: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)


class PaymentCheck(Base):
    __tablename__ = "payment_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProcessedPayment(Base):
    __tablename__ = "processed_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    invoice_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    payment_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    session = async_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


class TransactionLock:
    _locks: dict[int, asyncio.Lock] = {}
    _global_lock = asyncio.Lock()

    @classmethod
    async def acquire(cls, transaction_id: int) -> asyncio.Lock:
        async with cls._global_lock:
            if transaction_id not in cls._locks:
                cls._locks[transaction_id] = asyncio.Lock()
            return cls._locks[transaction_id]

    @classmethod
    async def release(cls, transaction_id: int) -> None:
        async with cls._global_lock:
            if transaction_id in cls._locks and not cls._locks[transaction_id].locked():
                del cls._locks[transaction_id]


class PaymentLock:
    _locks: dict[str, asyncio.Lock] = {}
    _global_lock = asyncio.Lock()

    @classmethod
    async def acquire(cls, payment_id: str) -> asyncio.Lock:
        async with cls._global_lock:
            if payment_id not in cls._locks:
                cls._locks[payment_id] = asyncio.Lock()
            return cls._locks[payment_id]

    @classmethod
    async def release(cls, payment_id: str) -> None:
        async with cls._global_lock:
            if payment_id in cls._locks and not cls._locks[payment_id].locked():
                del cls._locks[payment_id]


async def is_payment_processed(payment_id: str) -> bool:
    async with async_session() as session:
        result = await session.execute(
            select(ProcessedPayment).where(ProcessedPayment.payment_id == payment_id)
        )
        return result.scalar_one_or_none() is not None


async def mark_payment_processed(
    payment_type: str,
    payment_id: str,
    telegram_id: int,
    amount: float,
    invoice_id: int | None = None,
) -> bool:
    async with async_session() as session:
        existing = await session.execute(
            select(ProcessedPayment).where(ProcessedPayment.payment_id == payment_id)
        )
        if existing.scalar_one_or_none():
            return False
        
        payment = ProcessedPayment(
            payment_type=payment_type,
            payment_id=payment_id,
            telegram_id=telegram_id,
            amount=amount,
            invoice_id=invoice_id,
        )
        session.add(payment)
        await session.commit()
        return True
