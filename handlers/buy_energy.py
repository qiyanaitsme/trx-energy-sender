import asyncio
import logging
import uuid
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from sqlalchemy import select, and_

from config import config
from database import (
    async_session,
    Transaction,
    User,
    PaymentCheck,
    TransactionLock,
    PaymentLock,
    is_payment_processed,
    mark_payment_processed,
)
from services.tron_service import TronService
from services.lolz_service import LolzPaymentService, ENERGY_PACKAGES_RUB
from keyboards.main_menu import (
    get_energy_packages_keyboard,
    get_cancel_keyboard,
    get_back_keyboard,
    get_main_menu_keyboard,
    pad_text,
    W_FULL,
)
from utils.formatting import pad_message, is_admin

router = Router()
logger = logging.getLogger(__name__)

CHECK_COOLDOWN_SECONDS = 10


class BuyEnergyStates(StatesGroup):
    selecting_package = State()
    waiting_for_address = State()
    selecting_payment_method = State()
    waiting_for_payment = State()


def generate_payment_id() -> str:
    return f"trx_{uuid.uuid4().hex[:12]}"


def get_payment_method_keyboard(balance: float, price: int) -> InlineKeyboardMarkup:
    buttons = []
    if balance >= price:
        buttons.append([InlineKeyboardButton(
            text=pad_text(f"💰 С баланса ({balance:.0f} ₽)", W_FULL),
            callback_data="pay_balance"
        )])
    buttons.append([InlineKeyboardButton(
        text=pad_text("💳 Через LOLZ Market", W_FULL),
        callback_data="pay_lolz"
    )])
    buttons.append([InlineKeyboardButton(
        text=pad_text("❌ Отмена", W_FULL),
        callback_data="cancel_order"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_payment_keyboard(payment_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pad_text("💳 Оплатить", W_FULL), url=payment_url)],
            [InlineKeyboardButton(text=pad_text("✅ Я оплатил", W_FULL), callback_data="check_payment")],
            [InlineKeyboardButton(text=pad_text("❌ Отмена", W_FULL), callback_data="cancel_order")],
        ]
    )


async def check_bot_energy(energy_amount: int) -> tuple[bool, int, str]:
    tron_service = TronService()
    has_enough, available = await tron_service.has_enough_energy(energy_amount)
    if not has_enough:
        return False, available, f"Недостаточно энергии. Нужно: {energy_amount:,}, доступно: {available:,}"
    return True, available, ""


async def can_check_payment(transaction_id: int, telegram_id: int) -> tuple[bool, int]:
    async with async_session() as session:
        result = await session.execute(
            select(PaymentCheck)
            .where(
                and_(
                    PaymentCheck.transaction_id == transaction_id,
                    PaymentCheck.telegram_id == telegram_id,
                )
            )
            .order_by(PaymentCheck.checked_at.desc())
            .limit(1)
        )
        last_check = result.scalar_one_or_none()

        if last_check:
            elapsed = (datetime.utcnow() - last_check.checked_at).total_seconds()
            if elapsed < CHECK_COOLDOWN_SECONDS:
                return False, int(CHECK_COOLDOWN_SECONDS - elapsed)

        check = PaymentCheck(transaction_id=transaction_id, telegram_id=telegram_id)
        session.add(check)
        await session.commit()
        return True, 0


@router.callback_query(F.data == "buy_energy")
@router.message(Command("buy_energy"))
async def start_buy_energy(callback_or_message: CallbackQuery | Message, state: FSMContext) -> None:
    user_id = callback_or_message.from_user.id

    # Проверка на количество активных pending заказов
    async with async_session() as session:
        from sqlalchemy import func
        pending_count = await session.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.telegram_id == user_id,
                Transaction.status == "pending",
            )
        ) or 0

        if pending_count >= config.MAX_PENDING_ORDERS:
            text = pad_message(
                f"❌ <b>Слишком много активных заказов</b>\n\n"
                f"У тебя уже есть {pending_count} неоплаченных заказов.\n"
                f"Оплати или отмени их перед созданием нового."
            )
            if isinstance(callback_or_message, CallbackQuery):
                await callback_or_message.answer("❌ Слишком много активных заказов", show_alert=True)
            else:
                await callback_or_message.answer(text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(is_admin=is_admin(user_id)))
            return

    await state.set_state(BuyEnergyStates.selecting_package)

    text = pad_message(
        "⚡ <b>КУПИТЬ ENERGY</b>\n\n"
        "📦 <b>Выбери пакет:</b>\n\n"
        "├ ⚡ <b>70k</b> | 100₽ — для кошелька с USDT\n"
        "└ ⚡ <b>140k</b> | 200₽ — для пустого кошелька\n\n"
        "💡 Или выбери «Автоопределение» — бот сам рассчитает."
    )

    if isinstance(callback_or_message, CallbackQuery):
        await callback_or_message.message.edit_text(
            text, parse_mode="HTML", reply_markup=get_energy_packages_keyboard()
        )
        await callback_or_message.answer()
    else:
        await callback_or_message.answer(
            text, parse_mode="HTML", reply_markup=get_energy_packages_keyboard()
        )


def get_address_keyboard(has_saved_address: bool) -> InlineKeyboardMarkup:
    buttons = []
    if has_saved_address:
        buttons.append([InlineKeyboardButton(
            text=pad_text("✅ Использовать сохранённый", W_FULL),
            callback_data="use_saved_address"
        )])
    buttons.append([InlineKeyboardButton(
        text=pad_text("📝 Ввести другой адрес", W_FULL),
        callback_data="enter_new_address"
    )])
    buttons.append([InlineKeyboardButton(
        text=pad_text("❌ Отмена", W_FULL),
        callback_data="cancel_order"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data.startswith("energy_"))
async def select_energy_package(callback: CallbackQuery, state: FSMContext) -> None:
    package_key = callback.data.replace("energy_", "")

    if package_key == "auto":
        await state.update_data(auto_detect=True, energy_amount=None)
    else:
        package = ENERGY_PACKAGES_RUB.get(package_key)
        if not package:
            await callback.answer("❌ Неизвестный пакет", show_alert=True)
            return

        has_enough, available, error = await check_bot_energy(package["energy"])
        if not has_enough:
            await callback.answer(f"❌ {error}", show_alert=True)
            return

        await state.update_data(
            auto_detect=False,
            energy_amount=package["energy"],
            price_rub=package["price_rub"],
            package_name=package["name"],
        )

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        saved_address = user.tron_address if user else None

    if saved_address:
        await state.update_data(saved_address=saved_address)
        await callback.message.edit_text(
            pad_message(
                f"📍 <b>АДРЕС КОШЕЛЬКА</b>\n\n"
                f"У тебя сохранён адрес:\n"
                f"<code>{saved_address}</code>\n\n"
                f"Использовать его или ввести другой?"
            ),
            parse_mode="HTML",
            reply_markup=get_address_keyboard(True),
        )
    else:
        await state.set_state(BuyEnergyStates.waiting_for_address)
        await callback.message.edit_text(
            pad_message(
                "📍 <b>ВВЕДИ АДРЕС</b>\n\n"
                "Отправь адрес кошелька, <b>с которого</b> будешь переводить USDT TRC-20.\n\n"
                "⚠️ <i>Энергия нужна отправителю, не получателю!</i>"
            ),
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "use_saved_address")
async def use_saved_address(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    saved_address = data.get("saved_address")
    
    if not saved_address:
        await callback.answer("❌ Адрес не найден", show_alert=True)
        return
    
    await process_selected_address(callback, state, saved_address)


@router.callback_query(F.data == "enter_new_address")
async def enter_new_address(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BuyEnergyStates.waiting_for_address)
    await callback.message.edit_text(
        pad_message(
            "📍 <b>ВВЕДИ АДРЕС</b>\n\n"
            "Отправь адрес кошелька, <b>с которого</b> будешь переводить USDT TRC-20.\n\n"
            "⚠️ <i>Энергия нужна отправителю, не получателю!</i>"
        ),
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


@router.message(BuyEnergyStates.waiting_for_address)
async def process_address(message: Message, state: FSMContext) -> None:
    address = message.text.strip()
    tron_service = TronService()

    if not tron_service.validate_address(address):
        await message.answer(
            pad_message(
                "❌ <b>Неверный адрес</b>\n\n"
                "Адрес должен начинаться с <code>T</code> и содержать 34 символа."
            ),
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard(),
        )
        return

    await process_selected_address(message, state, address)


async def process_selected_address(
    event: CallbackQuery | Message,
    state: FSMContext,
    address: str,
) -> None:
    user_id = event.from_user.id
    data = await state.get_data()
    tron_service = TronService()

    if data.get("auto_detect"):
        calculation = await tron_service.calculate_energy_for_transfer(address)
        if "error" in calculation:
            text = pad_message(f"❌ Ошибка расчёта: {calculation['error']}")
            kb = get_back_keyboard()
            if isinstance(event, CallbackQuery):
                await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            else:
                await event.answer(text, parse_mode="HTML", reply_markup=kb)
            await state.clear()
            return

        has_usdt = calculation["has_usdt"]
        package = ENERGY_PACKAGES_RUB["70k"] if has_usdt else ENERGY_PACKAGES_RUB["140k"]
        energy_amount = package["energy"]
        price_rub = package["price_rub"]
        package_name = package["name"]

        has_enough, available, error = await check_bot_energy(energy_amount)
        if not has_enough:
            text = pad_message(f"❌ {error}")
            kb = get_back_keyboard()
            if isinstance(event, CallbackQuery):
                await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            else:
                await event.answer(text, parse_mode="HTML", reply_markup=kb)
            await state.clear()
            return
    else:
        energy_amount = data["energy_amount"]
        price_rub = data["price_rub"]
        package_name = data["package_name"]
        has_usdt = None

    async with async_session() as session:
        result = await session.execute(
            select(User.balance_rub).where(User.telegram_id == user_id)
        )
        balance = result.scalar_one_or_none() or 0

    await state.update_data(
        address=address,
        energy_amount=energy_amount,
        price_rub=price_rub,
        package_name=package_name,
        has_usdt=has_usdt,
    )
    await state.set_state(BuyEnergyStates.selecting_payment_method)

    status_text = ""
    if has_usdt is not None:
        status_text = f"\n├ Кошелёк: {'✅ есть USDT' if has_usdt else '❌ пустой'}"

    text = pad_message(
        f"💳 <b>СПОСОБ ОПЛАТЫ</b>\n\n"
        f"📦 Пакет: <b>⚡ {package_name}</b>{status_text}\n"
        f"├ Энергия: <b>{energy_amount:,}</b>\n"
        f"├ Стоимость: <b>{price_rub} ₽</b>\n"
        f"└ Аренда: <b>1 час</b>\n\n"
        f"📍 Адрес: <code>{address}</code>\n\n"
        f"💰 Твой баланс: <b>{balance:.0f} ₽</b>\n\n"
        f"Выбери способ оплаты:"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            text, parse_mode="HTML", reply_markup=get_payment_method_keyboard(balance, price_rub)
        )
        await event.answer()
    else:
        await event.answer(
            text, parse_mode="HTML", reply_markup=get_payment_method_keyboard(balance, price_rub)
        )


@router.callback_query(F.data == "pay_balance")
async def pay_with_balance(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state != BuyEnergyStates.selecting_payment_method.state:
        await callback.answer("❌ Ошибка состояния", show_alert=True)
        return

    data = await state.get_data()
    price_rub = data["price_rub"]
    energy_amount = data["energy_amount"]
    package_name = data.get("package_name")

    # Валидация цены на сервере — защита от манипуляции FSM state
    package = ENERGY_PACKAGES_RUB.get(package_name)
    if not package or package["price_rub"] != price_rub or package["energy"] != energy_amount:
        logger.error(f"Price manipulation attempt by user {callback.from_user.id}: state={price_rub}/{energy_amount}, expected={package}")
        await callback.answer("❌ Ошибка: данные заказа повреждены", show_alert=True)
        await state.clear()
        return

    has_enough, available, error = await check_bot_energy(energy_amount)
    if not has_enough:
        await callback.answer(f"❌ {error}", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user or user.balance_rub < price_rub:
            await callback.answer("❌ Недостаточно средств на балансе!", show_alert=True)
            return

        user.balance_rub -= price_rub

        transaction = Transaction(
            user_id=callback.from_user.id,
            telegram_id=callback.from_user.id,
            amount_energy=energy_amount,
            amount_trx=price_rub,
            recipient_address=data["address"],
            status="processing",
            payment_method="balance",
            paid_at=datetime.utcnow(),
            return_time=datetime.utcnow() + timedelta(seconds=config.ENERGY_RETURN_TIME),
            transaction_hash=f"balance_{generate_payment_id()}",
        )
        session.add(transaction)
        await session.commit()
        transaction_id = transaction.id

    await callback.message.edit_text(
        pad_message("✅ <b>Оплата с баланса!</b>\n\n⏳ Делегирую энергию..."),
        parse_mode="HTML",
    )
    await callback.answer()

    lock = await TransactionLock.acquire(transaction_id)
    async with lock:
        tron_service = TronService()
        result = await tron_service.delegate_energy(data["address"], energy_amount)

        if result.get("success"):
            delegate_hash = result.get("transaction_hash", "")

            async with async_session() as session:
                stmt = select(Transaction).where(Transaction.id == transaction_id)
                tx_result = await session.execute(stmt)
                tx = tx_result.scalar_one_or_none()
                if tx:
                    tx.status = "completed"
                    tx.delegate_hash = delegate_hash
                    tx.delegated_at = datetime.utcnow()
                    await session.commit()

            await callback.message.edit_text(
                pad_message(
                    f"🎉 <b>ГОТОВО!</b>\n\n"
                    f"⚡ Энергия делегирована!\n\n"
                    f"├ Пакет: <b>{data['package_name']}</b>\n"
                    f"├ Энергия: <b>{energy_amount:,}</b>\n"
                    f"├ Списано: <b>{price_rub} ₽</b>\n"
                    f"└ TX: <code>{delegate_hash[:16]}...</code>\n\n"
                    f"⏱ Энергия вернётся через 1 час.\n\n"
                    f"Теперь можешь переводить USDT! 🚀"
                ),
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard(is_admin=is_admin(callback.from_user.id)),
            )

            asyncio.create_task(
                schedule_energy_return(
                    callback.bot,
                    transaction_id,
                    data["address"],
                    energy_amount,
                    callback.from_user.id,
                    config.ENERGY_RETURN_TIME,
                )
            )
        else:
            async with async_session() as session:
                user_result = await session.execute(
                    select(User).where(User.telegram_id == callback.from_user.id)
                )
                user = user_result.scalar_one_or_none()
                if user:
                    user.balance_rub += price_rub

                tx_result = await session.execute(
                    select(Transaction).where(Transaction.id == transaction_id)
                )
                tx = tx_result.scalar_one_or_none()
                if tx:
                    tx.status = "failed"
                    tx.error_message = result.get("error", "Unknown error")

                await session.commit()

            await callback.message.edit_text(
                pad_message(
                    f"❌ <b>Ошибка делегирования</b>\n\n"
                    f"{result.get('error', 'Неизвестная ошибка')}\n\n"
                    f"💰 Средства возвращены на баланс."
                ),
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard(is_admin=is_admin(callback.from_user.id)),
            )

    await TransactionLock.release(transaction_id)
    await state.clear()


@router.callback_query(F.data == "pay_lolz")
async def pay_with_lolz(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state != BuyEnergyStates.selecting_payment_method.state:
        await callback.answer("❌ Ошибка состояния", show_alert=True)
        return

    data = await state.get_data()
    energy_amount = data["energy_amount"]

    has_enough, available, error = await check_bot_energy(energy_amount)
    if not has_enough:
        await callback.answer(f"❌ {error}", show_alert=True)
        return

    payment_id = generate_payment_id()

    lolz_service = LolzPaymentService()
    success_url = f"t.me/{config.BOT_USERNAME}" if config.BOT_USERNAME else ""
    invoice_result = await lolz_service.create_invoice(
        amount=data["price_rub"],
        payment_id=payment_id,
        comment=f"⚡ TRX Energy {data['package_name']}",
        url_success=success_url,
        merchant_id=config.LOLZ_MERCHANT_ID,
        lifetime=900,
    )

    if not invoice_result.get("success"):
        await callback.message.edit_text(
            pad_message(f"❌ Ошибка создания счёта: {invoice_result.get('error')}"),
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(is_admin=is_admin(callback.from_user.id)),
        )
        await callback.answer()
        await state.clear()
        return

    async with async_session() as session:
        transaction = Transaction(
            user_id=callback.from_user.id,
            telegram_id=callback.from_user.id,
            amount_energy=energy_amount,
            amount_trx=data["price_rub"],
            recipient_address=data["address"],
            status="pending",
            payment_method="lolz",
            lolz_invoice_id=invoice_result.get("invoice_id"),
            return_time=datetime.utcnow() + timedelta(seconds=config.ENERGY_RETURN_TIME),
            transaction_hash=payment_id,
        )
        session.add(transaction)
        await session.commit()
        transaction_id = transaction.id

    await state.update_data(
        payment_id=payment_id,
        invoice_id=invoice_result["invoice_id"],
        payment_url=invoice_result["payment_url"],
        transaction_id=transaction_id,
    )
    await state.set_state(BuyEnergyStates.waiting_for_payment)

    await callback.message.edit_text(
        pad_message(
            f"💳 <b>ОПЛАТА ЧЕРЕЗ LOLZ</b>\n\n"
            f"Сумма: <b>{data['price_rub']} ₽</b>\n\n"
            f"Нажми «Оплатить» и после оплаты вернись."
        ),
        parse_mode="HTML",
        reply_markup=get_payment_keyboard(invoice_result["payment_url"]),
    )
    await callback.answer()


@router.callback_query(F.data == "check_payment")
@router.message(Command("check_payment"))
async def check_payment(callback_or_message: CallbackQuery | Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state != BuyEnergyStates.waiting_for_payment.state:
        text = "❌ Нет активных заказов."
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.answer(text, show_alert=True)
        else:
            await callback_or_message.answer(
                pad_message(text),
                reply_markup=get_main_menu_keyboard(is_admin=is_admin(callback_or_message.from_user.id)),
            )
        return

    data = await state.get_data()
    transaction_id = data.get("transaction_id")
    payment_id = data.get("payment_id")
    price_rub = data.get("price_rub")
    energy_amount = data.get("energy_amount")
    package_name = data.get("package_name")

    # Валидация цены на сервере
    package = ENERGY_PACKAGES_RUB.get(package_name)
    if not package or package["price_rub"] != price_rub or package["energy"] != energy_amount:
        logger.error(f"Price mismatch for user {callback_or_message.from_user.id}: state={price_rub}, server={package}")
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.answer("❌ Ошибка: данные заказа повреждены", show_alert=True)
        await state.clear()
        return

    # Ранняя проверка с блокировкой для предотвращения race condition
    payment_lock = await PaymentLock.acquire(payment_id)
    async with payment_lock:
        if await is_payment_processed(payment_id):
            if isinstance(callback_or_message, CallbackQuery):
                await callback_or_message.answer("⚠️ Этот платёж уже обработан.", show_alert=True)
            await state.clear()
            await PaymentLock.release(payment_id)
            return

        can_check, wait_time = await can_check_payment(transaction_id, callback_or_message.from_user.id)
        if not can_check:
            if isinstance(callback_or_message, CallbackQuery):
                await callback_or_message.answer(f"⏳ Подожди {wait_time} сек.", show_alert=True)
            await PaymentLock.release(payment_id)
            return

        async with async_session() as session:
            tx_result = await session.execute(
                select(Transaction).where(Transaction.id == transaction_id)
            )
            tx = tx_result.scalar_one_or_none()
            if tx and tx.status in ("processing", "completed"):
                if isinstance(callback_or_message, CallbackQuery):
                    await callback_or_message.answer("⏳ Заказ уже обрабатывается...", show_alert=True)
                await PaymentLock.release(payment_id)
                return

        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.message.edit_text(
                pad_message("🔍 <b>Проверяю оплату...</b>"), parse_mode="HTML"
            )
            message = callback_or_message.message
            await callback_or_message.answer()
        else:
            message = await callback_or_message.answer(
                pad_message("🔍 <b>Проверяю оплату...</b>"), parse_mode="HTML"
            )

        lolz_service = LolzPaymentService()
        payment_found = False
        check_result = None

        for attempt in range(3):
            check_result = await lolz_service.check_invoice(
                invoice_id=data.get("invoice_id"),
                payment_id=payment_id,
                expected_amount=float(price_rub),
            )

            if check_result.get("amount_mismatch"):
                await message.edit_text(
                    pad_message(
                        f"❌ <b>Ошибка суммы</b>\n\n"
                        f"Ожидалось: <b>{price_rub} ₽</b>\n\n"
                        f"Обратитесь в поддержку."
                    ),
                    parse_mode="HTML",
                    reply_markup=get_main_menu_keyboard(is_admin=is_admin(callback_or_message.from_user.id)),
                )
                await state.clear()
                await PaymentLock.release(payment_id)
                return

            if check_result.get("success") and check_result.get("is_paid"):
                payment_found = True
                break

            if attempt < 2:
                await asyncio.sleep(2)

        if not payment_found:
            await message.edit_text(
                pad_message(
                    f"❌ <b>Оплата не найдена</b>\n\n"
                    f"Убедись, что оплатил <b>{price_rub} ₽</b>."
                ),
                parse_mode="HTML",
                reply_markup=get_payment_keyboard(data["payment_url"]),
            )
            await PaymentLock.release(payment_id)
            return

        # Повторная проверка после подтверждения оплаты
        if await is_payment_processed(payment_id):
            await message.edit_text(
                pad_message("⚠️ Этот платёж уже был обработан."),
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard(is_admin=is_admin(callback_or_message.from_user.id)),
            )
            await state.clear()
            await PaymentLock.release(payment_id)
            return

        lock = await TransactionLock.acquire(transaction_id)
        async with lock:
            async with async_session() as session:
                tx_result = await session.execute(
                    select(Transaction).where(Transaction.id == transaction_id)
                )
                tx = tx_result.scalar_one_or_none()

                if tx and tx.status in ("completed", "processing"):
                    await message.edit_text(
                        pad_message("⚠️ Этот заказ уже обработан."),
                        parse_mode="HTML",
                        reply_markup=get_main_menu_keyboard(is_admin=is_admin(callback_or_message.from_user.id)),
                    )
                    await state.clear()
                    await TransactionLock.release(transaction_id)
                    await PaymentLock.release(payment_id)
                    return

                if tx:
                    tx.status = "processing"
                    tx.paid_at = datetime.utcnow()
                    await session.commit()

            await message.edit_text(
                pad_message("✅ <b>Оплата получена!</b>\n\n⏳ Делегирую энергию..."),
                parse_mode="HTML",
            )

            tron_service = TronService()
            result = await tron_service.delegate_energy(data["address"], energy_amount)

            if result.get("success"):
                delegate_hash = result.get("transaction_hash", "")

                async with async_session() as session:
                    stmt = select(Transaction).where(Transaction.id == transaction_id)
                    tx_result = await session.execute(stmt)
                    transaction = tx_result.scalar_one_or_none()
                    if transaction:
                        transaction.status = "completed"
                        transaction.delegate_hash = delegate_hash
                        transaction.delegated_at = datetime.utcnow()
                        await session.commit()

                await mark_payment_processed(
                    payment_type="energy",
                    payment_id=payment_id,
                    telegram_id=callback_or_message.from_user.id,
                    amount=float(price_rub),
                    invoice_id=data.get("invoice_id"),
                )

                user_id = callback_or_message.from_user.id
                await message.edit_text(
                    pad_message(
                        f"🎉 <b>ГОТОВО!</b>\n\n"
                        f"⚡ Энергия делегирована!\n\n"
                        f"├ Пакет: <b>{package_name}</b>\n"
                        f"├ Энергия: <b>{energy_amount:,}</b>\n"
                        f"└ TX: <code>{delegate_hash[:16]}...</code>\n\n"
                        f"⏱ Энергия вернётся через 1 час.\n\n"
                        f"Теперь можешь переводить USDT! 🚀"
                    ),
                    parse_mode="HTML",
                    reply_markup=get_main_menu_keyboard(is_admin=is_admin(user_id)),
                )

                bot = callback_or_message.bot if isinstance(callback_or_message, CallbackQuery) else callback_or_message.bot
                asyncio.create_task(
                    schedule_energy_return(
                        bot,
                        transaction_id,
                        data["address"],
                        energy_amount,
                        callback_or_message.from_user.id,
                        config.ENERGY_RETURN_TIME,
                    )
                )
            else:
                async with async_session() as session:
                    tx_result = await session.execute(
                        select(Transaction).where(Transaction.id == transaction_id)
                    )
                    tx = tx_result.scalar_one_or_none()
                    if tx:
                        tx.status = "failed"
                        tx.error_message = result.get("error", "Unknown error")
                        tx.retry_count += 1
                        await session.commit()

                await message.edit_text(
                    pad_message(
                        f"❌ <b>Ошибка делегирования</b>\n\n"
                        f"{result.get('error', 'Неизвестная ошибка')}\n\n"
                        "Обратись в поддержку."
                    ),
                    parse_mode="HTML",
                    reply_markup=get_main_menu_keyboard(is_admin=is_admin(callback_or_message.from_user.id)),
                )

            await TransactionLock.release(transaction_id)
        await PaymentLock.release(payment_id)
    await state.clear()


@router.callback_query(F.data == "cancel_order")
async def cancel_order(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    transaction_id = data.get("transaction_id")

    if transaction_id:
        async with async_session() as session:
            tx_result = await session.execute(
                select(Transaction).where(Transaction.id == transaction_id)
            )
            tx = tx_result.scalar_one_or_none()
            if tx and tx.status == "pending":
                tx.status = "cancelled"
                await session.commit()

    await state.clear()
    await callback.message.edit_text(
        pad_message("❌ <b>Заказ отменён</b>"),
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin(callback.from_user.id)),
    )
    await callback.answer()


async def schedule_energy_return(
    bot,
    transaction_id: int,
    recipient_address: str,
    energy_amount: int,
    user_telegram_id: int,
    delay_seconds: int,
) -> None:
    logger.info(f"Scheduling energy return for tx #{transaction_id} in {delay_seconds}s")

    await asyncio.sleep(delay_seconds)

    lock = await TransactionLock.acquire(transaction_id)
    async with lock:
        async with async_session() as session:
            tx_result = await session.execute(
                select(Transaction).where(Transaction.id == transaction_id)
            )
            tx = tx_result.scalar_one_or_none()
            if tx and tx.is_energy_returned:
                logger.info(f"Energy already returned for tx #{transaction_id}")
                await TransactionLock.release(transaction_id)
                return

        tron_service = TronService()
        result = await tron_service.undelegate_energy(recipient_address, energy_amount)

        if result.get("success"):
            async with async_session() as session:
                stmt = select(Transaction).where(Transaction.id == transaction_id)
                tx_result = await session.execute(stmt)
                transaction = tx_result.scalar_one_or_none()
                if transaction:
                    transaction.is_energy_returned = True
                    transaction.status = "returned"
                    transaction.returned_at = datetime.utcnow()
                    transaction.undelegate_hash = result.get("transaction_hash", "")
                    await session.commit()

            try:
                await bot.send_message(
                    user_telegram_id,
                    pad_message(
                        f"✅ <b>Энергия возвращена</b>\n\n"
                        f"├ Заказ: <b>#{transaction_id}</b>\n"
                        f"├ Энергия: <b>{energy_amount:,}</b>\n"
                        f"├ Адрес: <code>{recipient_address[:8]}...{recipient_address[-6:]}</code>\n"
                        f"└ TX: <code>{result.get('transaction_hash', '')[:16]}...</code>\n\n"
                        f"⏱ Аренда завершена по расписанию.\n"
                        f"Спасибо за использование! 🙏"
                    ),
                    parse_mode="HTML",
                    reply_markup=get_main_menu_keyboard(),
                )
            except Exception as e:
                logger.warning(f"Failed to notify user {user_telegram_id}: {e}")

            logger.info(f"Energy returned for tx #{transaction_id}")
        else:
            logger.error(f"Failed to return energy for tx #{transaction_id}: {result.get('error')}")

            async with async_session() as session:
                tx_result = await session.execute(
                    select(Transaction).where(Transaction.id == transaction_id)
                )
                tx = tx_result.scalar_one_or_none()
                if tx:
                    tx.retry_count += 1
                    tx.error_message = f"Undelegate failed: {result.get('error')}"
                    await session.commit()

    await TransactionLock.release(transaction_id)
