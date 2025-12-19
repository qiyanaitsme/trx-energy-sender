from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func

from config import config
from database import async_session, User, Transaction
from services.tron_service import TronService
from keyboards.main_menu import get_profile_keyboard, get_main_menu_keyboard, get_back_keyboard
from utils.formatting import pad_message, is_admin

router = Router()


class ProfileStates(StatesGroup):
    waiting_for_address = State()


@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()

        total_orders = await session.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.telegram_id == user_id,
                Transaction.status == "completed",
            )
        ) or 0

        total_energy = await session.scalar(
            select(func.sum(Transaction.amount_energy)).where(
                Transaction.telegram_id == user_id,
                Transaction.status.in_(["completed", "returned"]),
            )
        ) or 0

        total_spent = await session.scalar(
            select(func.sum(Transaction.amount_trx)).where(
                Transaction.telegram_id == user_id,
                Transaction.status.in_(["completed", "returned"]),
            )
        ) or 0

    tron_address = user.tron_address if user and user.tron_address else "<i>Не указан</i>"
    reg_date = user.created_at.strftime("%d.%m.%Y") if user else "—"
    balance = user.balance_rub if user else 0

    await callback.message.edit_text(
        pad_message(
            f"👤 <b>ПРОФИЛЬ</b>\n\n"
            f"├ 🆔 ID: <code>{user_id}</code>\n"
            f"├ 📅 В боте с: {reg_date}\n"
            f"├ 💰 Баланс: <b>{balance:.0f} ₽</b>\n"
            f"└ 📍 Адрес TRX: {tron_address}\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"├ Заказов: <b>{total_orders}</b>\n"
            f"├ Куплено энергии: <b>{total_energy:,}</b>\n"
            f"└ Потрачено: <b>{total_spent:.0f} ₽</b>"
        ),
        parse_mode="HTML",
        reply_markup=get_profile_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "change_address")
async def change_address(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileStates.waiting_for_address)
    await callback.message.edit_text(
        pad_message(
            "📍 <b>ИЗМЕНИТЬ АДРЕС</b>\n\n"
            "Отправь свой Tron адрес (начинается с T):"
        ),
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "contacts")
async def show_contacts(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        pad_message(
            "📞 <b>КОНТАКТЫ</b>\n\n"
            "├ 💬 Поддержка: @inletahlolz\n"
            "├ 📢 Канал: @inletahlolz\n"
            "└ 👥 Чат: @inletahlolz\n\n"
            "⏰ Время ответа: до 24 часов\n\n"
            "❗ Перед обращением проверь:\n"
            "├ Правильность адреса кошелька\n"
            "├ Статус оплаты в истории\n"
            "└ Раздел «Правила» в меню"
        ),
        parse_mode="HTML",
        reply_markup=get_profile_keyboard(),
    )
    await callback.answer()


@router.message(ProfileStates.waiting_for_address)
async def process_new_address(message: Message, state: FSMContext) -> None:
    address = message.text.strip()
    tron_service = TronService()

    if not tron_service.validate_address(address):
        await message.answer(
            pad_message("❌ <b>Неверный адрес</b>\n\nПопробуй ещё раз:"),
            parse_mode="HTML",
            reply_markup=get_back_keyboard(),
        )
        return

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.tron_address = address
            await session.commit()

    await state.clear()
    await message.answer(
        pad_message(f"✅ <b>Адрес сохранён!</b>\n\n📍 <code>{address}</code>"),
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)),
    )
