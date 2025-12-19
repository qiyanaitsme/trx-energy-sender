import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from sqlalchemy import select, func

from config import config
from database import async_session, User, Transaction
from services.tron_service import TronService
from keyboards.main_menu import get_admin_keyboard, get_main_menu_keyboard, pad_text, W_FULL, W_HALF
from utils.formatting import pad_message

router = Router()
logger = logging.getLogger(__name__)

BANNED_USERS_PER_PAGE = 8


class AdminStates(StatesGroup):
    waiting_block_user_id = State()
    waiting_ban_reason = State()
    waiting_unblock_user_id = State()
    waiting_balance_user_id = State()
    waiting_balance_amount = State()
    waiting_broadcast_content = State()


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pad_text("📊 Статистика", W_FULL), callback_data="admin_stats")],
            [InlineKeyboardButton(text=pad_text("👥 Пользователи", W_FULL), callback_data="admin_users")],
            [InlineKeyboardButton(text=pad_text("🚫 Забаненные", W_FULL), callback_data="admin_banned_list")],
            [InlineKeyboardButton(text=pad_text("💰 Баланс кошелька", W_FULL), callback_data="admin_balance")],
            [
                InlineKeyboardButton(text=pad_text("🚫 Бан", W_HALF), callback_data="admin_block"),
                InlineKeyboardButton(text=pad_text("✅ Разбан", W_HALF), callback_data="admin_unblock"),
            ],
            [InlineKeyboardButton(text=pad_text("💵 Изменить баланс", W_FULL), callback_data="admin_set_balance")],
            [InlineKeyboardButton(text=pad_text("📢 Рассылка", W_FULL), callback_data="admin_broadcast")],
            [InlineKeyboardButton(text=pad_text("◀️ Назад", W_FULL), callback_data="back_to_menu")],
        ]
    )


def get_banned_users_keyboard(users: list[User], page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    for user in users:
        username = f"@{user.username}" if user.username else f"ID:{user.telegram_id}"
        btn_text = f"🚫 {username[:20]}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"banned_user_{user.telegram_id}")])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"banned_page_{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"banned_page_{page + 1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton(text=pad_text("◀️ Назад в админку", W_FULL), callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_user_profile_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pad_text("✅ Разбанить", W_FULL), callback_data=f"unban_user_{user_id}")],
            [InlineKeyboardButton(text=pad_text("◀️ К списку", W_FULL), callback_data="admin_banned_list")],
        ]
    )


def get_admin_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pad_text("◀️ Назад в админку", W_FULL), callback_data="admin_panel")]
        ]
    )


@router.message(Command("admin"))
@router.callback_query(F.data == "admin_panel")
async def cmd_admin(callback_or_message: CallbackQuery | Message, state: FSMContext) -> None:
    user_id = callback_or_message.from_user.id
    if not is_admin(user_id):
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.answer("❌ Доступ запрещён.", show_alert=True)
        else:
            await callback_or_message.answer(pad_message("❌ Доступ запрещён."))
        return

    await state.clear()
    
    text = pad_message("🔐 <b>АДМИН-ПАНЕЛЬ</b>\n\nВыбери действие:")
    
    if isinstance(callback_or_message, CallbackQuery):
        await callback_or_message.message.edit_text(
            text, parse_mode="HTML", reply_markup=get_admin_main_keyboard()
        )
        await callback_or_message.answer()
    else:
        await callback_or_message.answer(
            text, parse_mode="HTML", reply_markup=get_admin_main_keyboard()
        )


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён.", show_alert=True)
        return

    async with async_session() as session:
        users_count = await session.scalar(select(func.count(User.id)))
        blocked_count = await session.scalar(
            select(func.count(User.id)).where(User.is_blocked == True)
        )
        tx_count = await session.scalar(select(func.count(Transaction.id)))
        completed_count = await session.scalar(
            select(func.count(Transaction.id)).where(Transaction.status == "completed")
        )
        total_energy = await session.scalar(
            select(func.sum(Transaction.amount_energy)).where(Transaction.status == "completed")
        ) or 0
        total_rub = await session.scalar(
            select(func.sum(Transaction.amount_trx)).where(Transaction.status == "completed")
        ) or 0
        pending_count = await session.scalar(
            select(func.count(Transaction.id)).where(Transaction.status == "pending")
        )

    await callback.message.edit_text(
        pad_message(
            f"📊 <b>Статистика бота:</b>\n\n"
            f"👥 Пользователей: <b>{users_count}</b>\n"
            f"🚫 Заблокировано: <b>{blocked_count}</b>\n"
            f"📝 Всего транзакций: <b>{tx_count}</b>\n"
            f"✅ Завершённых: <b>{completed_count}</b>\n"
            f"⏳ Ожидающих: <b>{pending_count}</b>\n\n"
            f"⚡ Продано энергии: <b>{total_energy:,}</b>\n"
            f"💰 Заработано: <b>{total_rub:.0f} ₽</b>"
        ),
        parse_mode="HTML",
        reply_markup=get_admin_main_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён.", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(
            select(User).order_by(User.created_at.desc()).limit(10)
        )
        users = result.scalars().all()

    if not users:
        await callback.message.edit_text(
            pad_message("📭 Пользователей пока нет."),
            reply_markup=get_admin_main_keyboard(),
        )
        await callback.answer()
        return

    text = "👥 <b>Последние пользователи:</b>\n\n"
    for user in users:
        username = f"@{user.username}" if user.username else "—"
        status = "🚫" if user.is_blocked else "✅"
        balance = f"{user.balance_rub:.0f}₽"
        text += f"{status} <code>{user.telegram_id}</code> | {username} | {balance}\n"

    await callback.message.edit_text(
        pad_message(text), parse_mode="HTML", reply_markup=get_admin_main_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_balance")
async def admin_balance(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён.", show_alert=True)
        return

    tron_service = TronService()
    balance = await tron_service.get_energy_balance(config.TRON_WALLET_ADDRESS)

    if "error" in balance:
        await callback.message.edit_text(
            pad_message(f"❌ Ошибка получения баланса:\n{balance['error']}"),
            reply_markup=get_admin_main_keyboard(),
        )
        await callback.answer()
        return

    energy_available = balance.get("energy_limit", 0) - balance.get("energy_used", 0)
    trx_balance = balance.get("balance", 0) / 1_000_000

    await callback.message.edit_text(
        pad_message(
            f"💰 <b>Баланс кошелька бота:</b>\n\n"
            f"📍 Адрес: <code>{config.TRON_WALLET_ADDRESS[:10]}...</code>\n\n"
            f"💵 TRX: <b>{trx_balance:.2f}</b>\n"
            f"⚡ Доступная энергия: <b>{energy_available:,}</b>\n"
            f"📈 Лимит энергии: <b>{balance.get('energy_limit', 0):,}</b>"
        ),
        parse_mode="HTML",
        reply_markup=get_admin_main_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_block")
async def admin_block_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён.", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_block_user_id)
    await callback.message.edit_text(
        pad_message(
            "🚫 <b>Блокировка пользователя</b>\n\n"
            "Отправь Telegram ID пользователя для блокировки:"
        ),
        parse_mode="HTML",
        reply_markup=get_admin_back_keyboard(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_block_user_id)
async def admin_block_get_id(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            pad_message("❌ Неверный ID. Отправь число:"), reply_markup=get_admin_back_keyboard()
        )
        return

    if target_id in config.ADMIN_IDS:
        await message.answer(
            pad_message("❌ Нельзя заблокировать админа!"),
            reply_markup=get_admin_back_keyboard(),
        )
        await state.clear()
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()

        if not user:
            await message.answer(
                pad_message(f"❌ Пользователь с ID <code>{target_id}</code> не найден."),
                parse_mode="HTML",
                reply_markup=get_admin_back_keyboard(),
            )
            await state.clear()
            return

        if user.is_blocked:
            await message.answer(
                pad_message(f"⚠️ Пользователь <code>{target_id}</code> уже заблокирован."),
                parse_mode="HTML",
                reply_markup=get_admin_back_keyboard(),
            )
            await state.clear()
            return

    await state.update_data(ban_target_id=target_id)
    await state.set_state(AdminStates.waiting_ban_reason)
    
    await message.answer(
        pad_message(
            f"🚫 <b>Блокировка пользователя</b>\n\n"
            f"ID: <code>{target_id}</code>\n\n"
            f"Укажи причину блокировки:"
        ),
        parse_mode="HTML",
        reply_markup=get_admin_back_keyboard(),
    )


@router.message(AdminStates.waiting_ban_reason)
async def admin_block_user(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    target_id = data.get("ban_target_id")
    ban_reason = message.text.strip()[:500]
    admin_id = message.from_user.id

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()

        if not user:
            await message.answer(
                pad_message(f"❌ Пользователь с ID <code>{target_id}</code> не найден."),
                parse_mode="HTML",
                reply_markup=get_admin_back_keyboard(),
            )
            await state.clear()
            return

        user.is_blocked = True
        user.banned_at = datetime.utcnow()
        user.ban_reason = ban_reason
        user.banned_by = admin_id
        await session.commit()

    try:
        await bot.send_message(
            target_id,
            pad_message(
                f"🚫 <b>Вы заблокированы в боте</b>\n\n"
                f"Причина: {ban_reason}\n\n"
                f"Обратитесь в поддержку для разблокировки."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Failed to notify blocked user {target_id}: {e}")

    await message.answer(
        pad_message(
            f"✅ Пользователь <code>{target_id}</code> заблокирован.\n\n"
            f"Причина: {ban_reason}"
        ),
        parse_mode="HTML",
        reply_markup=get_admin_main_keyboard(),
    )
    await state.clear()


@router.callback_query(F.data == "admin_unblock")
async def admin_unblock_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён.", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_unblock_user_id)
    await callback.message.edit_text(
        pad_message(
            "✅ <b>Разблокировка пользователя</b>\n\n"
            "Отправь Telegram ID пользователя для разблокировки:"
        ),
        parse_mode="HTML",
        reply_markup=get_admin_back_keyboard(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_unblock_user_id)
async def admin_unblock_user(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            pad_message("❌ Неверный ID. Отправь число:"), reply_markup=get_admin_back_keyboard()
        )
        return

    await unban_user_by_id(target_id, message, state, bot)


async def unban_user_by_id(target_id: int, message: Message, state: FSMContext, bot: Bot) -> None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()

        if not user:
            await message.answer(
                pad_message(f"❌ Пользователь с ID <code>{target_id}</code> не найден."),
                parse_mode="HTML",
                reply_markup=get_admin_back_keyboard(),
            )
            await state.clear()
            return

        if not user.is_blocked:
            await message.answer(
                pad_message(f"⚠️ Пользователь <code>{target_id}</code> не заблокирован."),
                parse_mode="HTML",
                reply_markup=get_admin_back_keyboard(),
            )
            await state.clear()
            return

        user.is_blocked = False
        user.banned_at = None
        user.ban_reason = None
        user.banned_by = None
        await session.commit()

    try:
        await bot.send_message(
            target_id,
            pad_message("✅ <b>Вы разблокированы!</b>\n\nТеперь вы снова можете пользоваться ботом."),
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(),
        )
    except Exception as e:
        logger.warning(f"Failed to notify unblocked user {target_id}: {e}")

    await message.answer(
        pad_message(f"✅ Пользователь <code>{target_id}</code> разблокирован."),
        parse_mode="HTML",
        reply_markup=get_admin_main_keyboard(),
    )
    await state.clear()


@router.callback_query(F.data == "admin_banned_list")
async def admin_banned_list(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён.", show_alert=True)
        return

    await show_banned_page(callback, 0)


@router.callback_query(F.data.startswith("banned_page_"))
async def admin_banned_page(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён.", show_alert=True)
        return

    page = int(callback.data.split("_")[2])
    await show_banned_page(callback, page)


async def show_banned_page(callback: CallbackQuery, page: int) -> None:
    async with async_session() as session:
        total_count = await session.scalar(
            select(func.count(User.id)).where(User.is_blocked == True)
        )
        
        if total_count == 0:
            await callback.message.edit_text(
                pad_message("📭 Нет заблокированных пользователей."),
                reply_markup=get_admin_main_keyboard(),
            )
            await callback.answer()
            return

        total_pages = (total_count + BANNED_USERS_PER_PAGE - 1) // BANNED_USERS_PER_PAGE
        offset = page * BANNED_USERS_PER_PAGE

        result = await session.execute(
            select(User)
            .where(User.is_blocked == True)
            .order_by(User.banned_at.desc().nulls_last())
            .offset(offset)
            .limit(BANNED_USERS_PER_PAGE)
        )
        users = result.scalars().all()

    await callback.message.edit_text(
        pad_message(
            f"🚫 <b>Заблокированные пользователи</b>\n\n"
            f"Всего: <b>{total_count}</b>\n\n"
            f"Нажми на пользователя для просмотра профиля:"
        ),
        parse_mode="HTML",
        reply_markup=get_banned_users_keyboard(users, page, total_pages),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("banned_user_"))
async def admin_view_banned_user(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён.", show_alert=True)
        return

    target_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("❌ Пользователь не найден.", show_alert=True)
            return

        tx_count = await session.scalar(
            select(func.count(Transaction.id))
            .where(Transaction.telegram_id == target_id)
            .where(Transaction.status == "completed")
        )
        
        total_spent = await session.scalar(
            select(func.sum(Transaction.amount_trx))
            .where(Transaction.telegram_id == target_id)
            .where(Transaction.status == "completed")
        ) or 0

    username = f"@{user.username}" if user.username else "—"
    wallet = f"<code>{user.tron_address}</code>" if user.tron_address else "—"
    created = user.created_at.strftime("%d.%m.%Y %H:%M") if user.created_at else "—"
    banned_at = user.banned_at.strftime("%d.%m.%Y %H:%M") if user.banned_at else "—"
    ban_reason = user.ban_reason or "Не указана"
    deposited = user.total_deposited or 0

    await callback.message.edit_text(
        pad_message(
            f"👤 <b>Профиль пользователя</b>\n\n"
            f"├ ID: <code>{user.telegram_id}</code>\n"
            f"├ Username: {username}\n"
            f"├ Кошелёк: {wallet}\n"
            f"├ Баланс: <b>{user.balance_rub:.0f} ₽</b>\n"
            f"├ Пополнено всего: <b>{deposited:.0f} ₽</b>\n"
            f"├ Покупок: <b>{tx_count}</b>\n"
            f"├ Потрачено: <b>{total_spent:.0f} ₽</b>\n"
            f"├ Регистрация: {created}\n"
            f"├ Последняя активность: {user.last_activity.strftime('%d.%m.%Y %H:%M') if user.last_activity else '—'}\n\n"
            f"🚫 <b>Информация о бане:</b>\n"
            f"├ Дата бана: {banned_at}\n"
            f"└ Причина: {ban_reason}"
        ),
        parse_mode="HTML",
        reply_markup=get_user_profile_keyboard(user.telegram_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("unban_user_"))
async def admin_unban_from_profile(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён.", show_alert=True)
        return

    target_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("❌ Пользователь не найден.", show_alert=True)
            return

        if not user.is_blocked:
            await callback.answer("⚠️ Пользователь не заблокирован.", show_alert=True)
            return

        user.is_blocked = False
        user.banned_at = None
        user.ban_reason = None
        user.banned_by = None
        await session.commit()

    try:
        await bot.send_message(
            target_id,
            pad_message("✅ <b>Вы разблокированы!</b>\n\nТеперь вы снова можете пользоваться ботом."),
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(),
        )
    except Exception as e:
        logger.warning(f"Failed to notify unblocked user {target_id}: {e}")

    await callback.answer("✅ Пользователь разблокирован!", show_alert=True)
    await show_banned_page(callback, 0)


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "admin_set_balance")
async def admin_set_balance_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён.", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_balance_user_id)
    await callback.message.edit_text(
        pad_message(
            "💵 <b>Изменение баланса</b>\n\n"
            "Отправь Telegram ID пользователя:"
        ),
        parse_mode="HTML",
        reply_markup=get_admin_back_keyboard(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_balance_user_id)
async def admin_balance_get_user(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            pad_message("❌ Неверный ID. Отправь число:"), reply_markup=get_admin_back_keyboard()
        )
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()

        if not user:
            await message.answer(
                pad_message(f"❌ Пользователь с ID <code>{target_id}</code> не найден."),
                parse_mode="HTML",
                reply_markup=get_admin_back_keyboard(),
            )
            await state.clear()
            return

        await state.update_data(target_user_id=target_id, current_balance=user.balance_rub)
        await state.set_state(AdminStates.waiting_balance_amount)

        await message.answer(
            pad_message(
                f"👤 Пользователь: <code>{target_id}</code>\n"
                f"💰 Текущий баланс: <b>{user.balance_rub:.0f} ₽</b>\n\n"
                f"Отправь новый баланс (число в рублях):\n"
                f"<i>Например: 500 или +100 или -50</i>"
            ),
            parse_mode="HTML",
            reply_markup=get_admin_back_keyboard(),
        )


@router.message(AdminStates.waiting_balance_amount)
async def admin_balance_set(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    target_id = data["target_user_id"]
    current_balance = data["current_balance"]
    
    text = message.text.strip()
    
    try:
        if text.startswith("+"):
            delta = float(text[1:])
            new_balance = current_balance + delta
        elif text.startswith("-"):
            delta = float(text[1:])
            new_balance = current_balance - delta
        else:
            new_balance = float(text)
        
        if new_balance < 0:
            new_balance = 0
        if new_balance > 10_000_000:
            await message.answer(
                pad_message("❌ Максимальный баланс: 10,000,000 ₽"),
                reply_markup=get_admin_back_keyboard(),
            )
            return
    except ValueError:
        await message.answer(
            pad_message(
                "❌ Неверный формат. Отправь число:\n"
                "<i>Например: 500 или +100 или -50</i>"
            ),
            parse_mode="HTML",
            reply_markup=get_admin_back_keyboard(),
        )
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()

        if user:
            user.balance_rub = new_balance
            diff = new_balance - current_balance
            if diff > 0:
                user.total_deposited = (user.total_deposited or 0) + diff
            await session.commit()

    diff = new_balance - current_balance
    if diff > 0:
        try:
            await bot.send_message(
                target_id,
                pad_message(
                    f"💰 <b>Баланс пополнен администратором!</b>\n\n"
                    f"├ Сумма: <b>+{diff:.0f} ₽</b>\n"
                    f"└ Новый баланс: <b>{new_balance:.0f} ₽</b>"
                ),
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard(),
            )
        except Exception as e:
            logger.warning(f"Failed to notify user {target_id} about balance change: {e}")
    elif diff < 0:
        try:
            await bot.send_message(
                target_id,
                pad_message(
                    f"💸 <b>Баланс изменён администратором</b>\n\n"
                    f"├ Сумма: <b>{diff:.0f} ₽</b>\n"
                    f"└ Новый баланс: <b>{new_balance:.0f} ₽</b>"
                ),
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard(),
            )
        except Exception as e:
            logger.warning(f"Failed to notify user {target_id} about balance change: {e}")

    await message.answer(
        pad_message(
            f"✅ Баланс пользователя <code>{target_id}</code> изменён:\n"
            f"├ Было: <b>{current_balance:.0f} ₽</b>\n"
            f"└ Стало: <b>{new_balance:.0f} ₽</b>"
        ),
        parse_mode="HTML",
        reply_markup=get_admin_main_keyboard(),
    )
    await state.clear()


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён.", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_broadcast_content)
    await callback.message.edit_text(
        pad_message(
            "📢 <b>Рассылка</b>\n\n"
            "Отправь сообщение для рассылки.\n\n"
            "Поддерживается:\n"
            "├ Текст (с HTML-разметкой)\n"
            "├ Фото с подписью\n"
            "├ Видео с подписью\n"
            "└ Документы\n\n"
            "<i>Сообщение будет отправлено всем пользователям.</i>"
        ),
        parse_mode="HTML",
        reply_markup=get_admin_back_keyboard(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_broadcast_content)
async def admin_broadcast_send(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return

    import asyncio

    async with async_session() as session:
        result = await session.execute(
            select(User.telegram_id).where(User.is_blocked == False)
        )
        user_ids = [row[0] for row in result.fetchall()]

    if not user_ids:
        await message.answer(
            pad_message("📭 Нет пользователей для рассылки."), reply_markup=get_admin_main_keyboard()
        )
        await state.clear()
        return

    status_msg = await message.answer(
        pad_message(f"📤 Начинаю рассылку для {len(user_ids)} пользователей...")
    )

    sent = 0
    failed = 0

    for i, user_id in enumerate(user_ids):
        try:
            if message.photo:
                await bot.send_photo(
                    user_id,
                    photo=message.photo[-1].file_id,
                    caption=message.caption,
                    parse_mode="HTML",
                )
            elif message.video:
                await bot.send_video(
                    user_id,
                    video=message.video.file_id,
                    caption=message.caption,
                    parse_mode="HTML",
                )
            elif message.document:
                await bot.send_document(
                    user_id,
                    document=message.document.file_id,
                    caption=message.caption,
                    parse_mode="HTML",
                )
            elif message.animation:
                await bot.send_animation(
                    user_id,
                    animation=message.animation.file_id,
                    caption=message.caption,
                    parse_mode="HTML",
                )
            elif message.sticker:
                await bot.send_sticker(user_id, sticker=message.sticker.file_id)
            else:
                await bot.send_message(user_id, message.text, parse_mode="HTML")
            sent += 1
        except Exception as e:
            logger.warning(f"Failed to send broadcast to {user_id}: {e}")
            failed += 1

        if (i + 1) % 25 == 0:
            await asyncio.sleep(1)

    await status_msg.edit_text(
        pad_message(
            f"📢 <b>Рассылка завершена!</b>\n\n"
            f"✅ Отправлено: <b>{sent}</b>\n"
            f"❌ Ошибок: <b>{failed}</b>"
        ),
        parse_mode="HTML",
        reply_markup=get_admin_main_keyboard(),
    )
    await state.clear()


@router.message(Command("broadcast"))
async def cmd_broadcast_legacy(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(pad_message("❌ Доступ запрещён."))
        return

    await message.answer(
        pad_message("📢 Используй админ-панель для рассылки:\n/admin → Рассылка"),
        reply_markup=get_admin_main_keyboard(),
    )
