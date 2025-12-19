import asyncio
import logging
import uuid

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from sqlalchemy import select

from config import config
from database import async_session, User, PaymentLock, is_payment_processed, mark_payment_processed, get_db_session
from services.lolz_service import LolzPaymentService
from keyboards.main_menu import pad_text, get_main_menu_keyboard, W_FULL
from utils.formatting import pad_message, is_admin

router = Router()
logger = logging.getLogger(__name__)


class BalanceStates(StatesGroup):
    waiting_amount = State()
    waiting_payment = State()


def get_topup_amounts_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="100 ₽", callback_data="topup_100"),
                InlineKeyboardButton(text="200 ₽", callback_data="topup_200"),
                InlineKeyboardButton(text="500 ₽", callback_data="topup_500"),
            ],
            [
                InlineKeyboardButton(text="1000 ₽", callback_data="topup_1000"),
                InlineKeyboardButton(text="Своя сумма", callback_data="topup_custom"),
            ],
            [InlineKeyboardButton(text=pad_text("◀️ Назад", W_FULL), callback_data="back_to_menu")],
        ]
    )


def get_topup_payment_keyboard(payment_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pad_text("💳 Оплатить", W_FULL), url=payment_url)],
            [InlineKeyboardButton(text=pad_text("✅ Я оплатил", W_FULL), callback_data="check_topup")],
            [InlineKeyboardButton(text=pad_text("❌ Отмена", W_FULL), callback_data="cancel_topup")],
        ]
    )


@router.callback_query(F.data == "topup_balance")
async def start_topup(callback: CallbackQuery, state: FSMContext) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(User.balance_rub).where(User.telegram_id == callback.from_user.id)
        )
        balance = result.scalar_one_or_none() or 0

    await callback.message.edit_text(
        pad_message(
            f"💰 <b>ПОПОЛНЕНИЕ БАЛАНСА</b>\n\n"
            f"Текущий баланс: <b>{balance:.0f} ₽</b>\n\n"
            f"Выбери сумму пополнения:"
        ),
        parse_mode="HTML",
        reply_markup=get_topup_amounts_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("topup_"))
async def select_topup_amount(callback: CallbackQuery, state: FSMContext) -> None:
    amount_str = callback.data.replace("topup_", "")
    
    if amount_str == "custom":
        await state.set_state(BalanceStates.waiting_amount)
        await callback.message.edit_text(
            pad_message(
                "💰 <b>Своя сумма</b>\n\n"
                "Введи сумму пополнения в рублях (минимум 50):"
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=pad_text("◀️ Назад", W_FULL), callback_data="topup_balance")]
                ]
            ),
        )
        await callback.answer()
        return
    
    try:
        amount = int(amount_str)
    except ValueError:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    await process_topup(callback, state, amount)


@router.message(BalanceStates.waiting_amount)
async def custom_amount_input(message: Message, state: FSMContext) -> None:
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            await message.answer(pad_message("❌ Сумма должна быть положительной. Попробуй ещё раз:"))
            return
        if amount < 50:
            await message.answer(pad_message("❌ Минимальная сумма — 50 ₽. Попробуй ещё раз:"))
            return
        if amount > 100000:
            await message.answer(pad_message("❌ Максимальная сумма — 100,000 ₽. Попробуй ещё раз:"))
            return
    except ValueError:
        await message.answer(pad_message("❌ Введи число. Попробуй ещё раз:"))
        return
    
    await process_topup(message, state, amount)


async def process_topup(event: CallbackQuery | Message, state: FSMContext, amount: int) -> None:
    user_id = event.from_user.id
    payment_id = f"topup_{uuid.uuid4().hex[:12]}"
    
    lolz_service = LolzPaymentService()
    success_url = f"t.me/{config.BOT_USERNAME}" if config.BOT_USERNAME else ""
    invoice_result = await lolz_service.create_invoice(
        amount=amount,
        payment_id=payment_id,
        comment=f"Пополнение баланса TRX Energy Bot",
        url_success=success_url,
        merchant_id=config.LOLZ_MERCHANT_ID,
        lifetime=900,
    )
    
    if not invoice_result.get("success"):
        text = pad_message(f"❌ Ошибка создания счёта: {invoice_result.get('error', 'Неизвестная ошибка')}")
        kb = get_main_menu_keyboard(is_admin=is_admin(user_id))
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        else:
            await event.answer(text, parse_mode="HTML", reply_markup=kb)
        await state.clear()
        return
    
    await state.update_data(
        topup_amount=amount,
        payment_id=payment_id,
        invoice_id=invoice_result["invoice_id"],
        payment_url=invoice_result["payment_url"],
    )
    await state.set_state(BalanceStates.waiting_payment)
    
    text = pad_message(
        f"💳 <b>ОПЛАТА</b>\n\n"
        f"Сумма: <b>{amount} ₽</b>\n\n"
        f"Нажми «Оплатить» для перехода к оплате.\n"
        f"После оплаты вернись и нажми «✅ Я оплатил»"
    )
    
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            text, parse_mode="HTML", reply_markup=get_topup_payment_keyboard(invoice_result["payment_url"])
        )
        await event.answer()
    else:
        await event.answer(
            text, parse_mode="HTML", reply_markup=get_topup_payment_keyboard(invoice_result["payment_url"])
        )


@router.callback_query(F.data == "check_topup")
async def check_topup_payment(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state != BalanceStates.waiting_payment.state:
        await callback.answer("❌ Нет активного пополнения.", show_alert=True)
        return
    
    data = await state.get_data()
    payment_id = data.get("payment_id")
    topup_amount = data.get("topup_amount")
    
    if await is_payment_processed(payment_id):
        await callback.answer("⚠️ Этот платёж уже обработан.", show_alert=True)
        await state.clear()
        return
    
    await callback.message.edit_text(
        pad_message("🔍 <b>Проверяю оплату...</b>"), parse_mode="HTML"
    )
    await callback.answer()
    
    lolz_service = LolzPaymentService()
    
    for attempt in range(3):
        check_result = await lolz_service.check_invoice(
            invoice_id=data.get("invoice_id"),
            payment_id=payment_id,
            expected_amount=float(topup_amount),
        )
        
        if check_result.get("amount_mismatch"):
            await callback.message.edit_text(
                pad_message(
                    f"❌ <b>Ошибка суммы</b>\n\n"
                    f"Ожидалось: <b>{topup_amount} ₽</b>\n"
                    f"Получено: <b>{check_result.get('amount', 0)} ₽</b>\n\n"
                    f"Обратитесь в поддержку."
                ),
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard(is_admin=is_admin(callback.from_user.id)),
            )
            await state.clear()
            return
        
        if check_result.get("success") and check_result.get("is_paid"):
            lock = await PaymentLock.acquire(payment_id)
            async with lock:
                if await is_payment_processed(payment_id):
                    await callback.message.edit_text(
                        pad_message("⚠️ Этот платёж уже был обработан."),
                        parse_mode="HTML",
                        reply_markup=get_main_menu_keyboard(is_admin=is_admin(callback.from_user.id)),
                    )
                    await state.clear()
                    await PaymentLock.release(payment_id)
                    return
                
                async with async_session() as session:
                    result = await session.execute(
                        select(User).where(User.telegram_id == callback.from_user.id)
                    )
                    user = result.scalar_one_or_none()
                    
                    if user:
                        user.balance_rub += topup_amount
                        user.total_deposited = (user.total_deposited or 0) + topup_amount
                        new_balance = user.balance_rub
                        await session.commit()
                    else:
                        new_balance = topup_amount
                
                await mark_payment_processed(
                    payment_type="topup",
                    payment_id=payment_id,
                    telegram_id=callback.from_user.id,
                    amount=float(topup_amount),
                    invoice_id=data.get("invoice_id"),
                )
            
            await PaymentLock.release(payment_id)
            
            await callback.message.edit_text(
                pad_message(
                    f"✅ <b>Вы успешно пополнили баланс!</b>\n\n"
                    f"├ Сумма: <b>+{topup_amount} ₽</b>\n"
                    f"└ Новый баланс: <b>{new_balance:.0f} ₽</b>\n\n"
                    f"Теперь можешь покупать энергию! ⚡"
                ),
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard(is_admin=is_admin(callback.from_user.id)),
            )
            await state.clear()
            return
        
        await asyncio.sleep(2)
    
    await callback.message.edit_text(
        pad_message(
            "❌ <b>Оплата не найдена</b>\n\n"
            f"Убедись, что оплатил счёт на <b>{topup_amount} ₽</b>.\n\n"
            "Подожди 1-2 минуты и попробуй снова."
        ),
        parse_mode="HTML",
        reply_markup=get_topup_payment_keyboard(data["payment_url"]),
    )


@router.callback_query(F.data == "cancel_topup")
async def cancel_topup(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        pad_message("❌ <b>Пополнение отменено</b>"),
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin(callback.from_user.id)),
    )
    await callback.answer()
