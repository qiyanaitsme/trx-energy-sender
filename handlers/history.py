from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from database import async_session, Transaction
from keyboards.main_menu import get_main_menu_keyboard
from utils.formatting import pad_message, is_admin

router = Router()


STATUS_EMOJI = {
    "pending": "⏳",
    "completed": "✅",
    "failed": "❌",
    "returned": "↩️",
}

STATUS_TEXT = {
    "pending": "Ожидает",
    "completed": "Активна",
    "failed": "Ошибка",
    "returned": "Возвращена",
}


@router.callback_query(F.data == "history")
@router.message(Command("history"))
async def cmd_history(callback_or_message: CallbackQuery | Message) -> None:
    user_id = callback_or_message.from_user.id

    async with async_session() as session:
        result = await session.execute(
            select(Transaction)
            .where(Transaction.telegram_id == user_id)
            .order_by(Transaction.created_at.desc())
            .limit(10)
        )
        transactions = result.scalars().all()

    if not transactions:
        text = (
            "📋 <b>ИСТОРИЯ</b>\n\n"
            "📭 У тебя пока нет транзакций.\n\n"
            "Нажми «⚡ Купить Energy» чтобы начать!"
        )
    else:
        text = "📋 <b>ИСТОРИЯ ОПЕРАЦИЙ</b>\n\n"
        for tx in transactions:
            emoji = STATUS_EMOJI.get(tx.status, "❓")
            status = STATUS_TEXT.get(tx.status, tx.status)
            date_str = tx.created_at.strftime("%d.%m %H:%M")
            text += (
                f"{emoji} <b>#{tx.id}</b> | {date_str}\n"
                f"├ ⚡ {tx.amount_energy:,} энергии\n"
                f"├ 💰 {tx.amount_trx:.0f} ₽\n"
                f"└ 📍 {status}\n\n"
            )

    if isinstance(callback_or_message, CallbackQuery):
        await callback_or_message.message.edit_text(
            pad_message(text),
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(is_admin=is_admin(user_id)),
        )
        await callback_or_message.answer()
    else:
        await callback_or_message.answer(
            pad_message(text),
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(is_admin=is_admin(user_id)),
        )
