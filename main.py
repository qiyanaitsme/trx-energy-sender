import asyncio
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, and_

from config import config
from database import init_db, async_session, Transaction, TransactionLock
from services.tron_service import TronService
from handlers import (
    start_router,
    buy_energy_router,
    check_energy_router,
    history_router,
    admin_router,
    profile_router,
    balance_router,
)
from middlewares import BlockCheckMiddleware


def setup_logging() -> None:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_dir / "bot.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    error_handler = RotatingFileHandler(
        log_dir / "errors.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)

    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger(__name__)


async def return_energy_job(bot: Bot) -> None:
    logger.info("Running energy return job...")

    async with async_session() as session:
        result = await session.execute(
            select(Transaction).where(
                and_(
                    Transaction.return_time <= datetime.utcnow(),
                    Transaction.is_energy_returned == False,
                    Transaction.status == "completed",
                )
            )
        )
        transactions = result.scalars().all()

        if not transactions:
            logger.debug("No energy to return.")
            return

        logger.info(f"Found {len(transactions)} transactions to return energy.")
        tron_service = TronService()

        for tx in transactions:
            lock = await TransactionLock.acquire(tx.id)
            async with lock:
                try:
                    tx_check = await session.execute(
                        select(Transaction).where(Transaction.id == tx.id)
                    )
                    tx_fresh = tx_check.scalar_one_or_none()
                    if tx_fresh and tx_fresh.is_energy_returned:
                        logger.debug(f"TX #{tx.id} already returned, skipping.")
                        continue

                    undelegate_result = await tron_service.undelegate_energy(
                        tx.recipient_address,
                        tx.amount_energy,
                    )

                    if undelegate_result.get("success"):
                        tx.is_energy_returned = True
                        tx.status = "returned"
                        tx.returned_at = datetime.utcnow()
                        tx.undelegate_hash = undelegate_result.get("transaction_hash", "")
                        tx_hash = undelegate_result.get("transaction_hash", "")

                        try:
                            await bot.send_message(
                                tx.telegram_id,
                                f"✅ <b>Энергия возвращена</b>\n\n"
                                f"├ Заказ: <b>#{tx.id}</b>\n"
                                f"├ Энергия: <b>{tx.amount_energy:,}</b>\n"
                                f"├ Адрес: <code>{tx.recipient_address[:8]}...{tx.recipient_address[-6:]}</code>\n"
                                f"└ TX: <code>{tx_hash[:16]}...</code>\n\n"
                                f"⏱ Аренда завершена по расписанию.\n"
                                f"Спасибо за использование! 🙏",
                                parse_mode="HTML",
                            )
                        except Exception as e:
                            logger.warning(f"Failed to notify user {tx.telegram_id}: {e}")

                        logger.info(f"Energy returned for tx #{tx.id}")
                    else:
                        tx.retry_count += 1
                        tx.error_message = f"Scheduler: {undelegate_result.get('error')}"
                        logger.error(
                            f"Failed to return energy for tx #{tx.id}: "
                            f"{undelegate_result.get('error')}"
                        )

                except Exception as e:
                    logger.error(f"Error returning energy for tx #{tx.id}: {e}")
                    tx.retry_count += 1
                    tx.error_message = str(e)

            await TransactionLock.release(tx.id)

        await session.commit()


async def check_failed_transactions(bot: Bot) -> None:
    logger.info("Checking failed transactions...")

    async with async_session() as session:
        result = await session.execute(
            select(Transaction).where(
                and_(
                    Transaction.status == "failed",
                    Transaction.retry_count < 3,
                    Transaction.paid_at.isnot(None),
                )
            )
        )
        failed_txs = result.scalars().all()

        if not failed_txs:
            return

        logger.info(f"Found {len(failed_txs)} failed transactions to retry.")
        tron_service = TronService()

        for tx in failed_txs:
            lock = await TransactionLock.acquire(tx.id)
            async with lock:
                try:
                    has_enough, available = await tron_service.has_enough_energy(tx.amount_energy)
                    if not has_enough:
                        logger.warning(f"Not enough energy to retry tx #{tx.id}")
                        continue

                    result = await tron_service.delegate_energy(tx.recipient_address, tx.amount_energy)

                    if result.get("success"):
                        tx.status = "completed"
                        tx.delegate_hash = result.get("transaction_hash", "")
                        tx.delegated_at = datetime.utcnow()
                        tx.error_message = None

                        try:
                            await bot.send_message(
                                tx.telegram_id,
                                f"✅ <b>Заказ #{tx.id} обработан!</b>\n\n"
                                f"Энергия ({tx.amount_energy:,}) делегирована.\n"
                                f"TX: <code>{tx.delegate_hash[:16]}...</code>",
                                parse_mode="HTML",
                            )
                        except Exception as e:
                            logger.warning(f"Failed to notify user {tx.telegram_id}: {e}")

                        logger.info(f"Retried tx #{tx.id} successfully")
                    else:
                        tx.retry_count += 1
                        tx.error_message = result.get("error")
                        logger.error(f"Retry failed for tx #{tx.id}: {result.get('error')}")

                except Exception as e:
                    logger.error(f"Error retrying tx #{tx.id}: {e}")
                    tx.retry_count += 1

            await TransactionLock.release(tx.id)

        await session.commit()


async def log_bot_status() -> None:
    tron_service = TronService()
    balance = await tron_service.get_energy_balance(config.TRON_WALLET_ADDRESS)

    if "error" not in balance:
        available = balance.get("energy_available", 0)
        trx = balance.get("balance", 0) / 1_000_000
        logger.info(f"Bot status: Energy={available:,}, TRX={trx:.2f}")
    else:
        logger.warning(f"Failed to get bot status: {balance.get('error')}")


async def main() -> None:
    logger.info("=" * 50)
    logger.info("Starting Tron Energy Bot...")
    logger.info(f"Network: {config.TRON_NETWORK}")
    logger.info(f"Wallet: {config.TRON_WALLET_ADDRESS[:10]}...")
    logger.info("=" * 50)

    if not config.BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set in .env")
    if not config.TRON_WALLET_ADDRESS:
        raise ValueError("TRON_WALLET_ADDRESS is not set in .env")
    if not config.TRON_PRIVATE_KEY:
        raise ValueError("TRON_PRIVATE_KEY is not set in .env")

    await init_db()
    logger.info("Database initialized.")

    await log_bot_status()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(BlockCheckMiddleware())
    dp.callback_query.middleware(BlockCheckMiddleware())

    dp.include_router(start_router)
    dp.include_router(buy_energy_router)
    dp.include_router(check_energy_router)
    dp.include_router(history_router)
    dp.include_router(admin_router)
    dp.include_router(profile_router)
    dp.include_router(balance_router)

    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        return_energy_job,
        "interval",
        minutes=5,
        args=[bot],
        id="return_energy",
        replace_existing=True,
    )

    scheduler.add_job(
        check_failed_transactions,
        "interval",
        minutes=10,
        args=[bot],
        id="retry_failed",
        replace_existing=True,
    )

    scheduler.add_job(
        log_bot_status,
        "interval",
        hours=1,
        id="log_status",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with 3 jobs.")

    logger.info("Bot is running... Press Ctrl+C to stop.")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except asyncio.CancelledError:
        pass
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
