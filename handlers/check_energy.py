from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from services.tron_service import TronService
from keyboards.main_menu import get_back_keyboard, get_main_menu_keyboard
from utils.formatting import pad_message, is_admin

router = Router()


class CheckEnergyStates(StatesGroup):
    waiting_for_address = State()


@router.callback_query(F.data == "check_energy")
@router.message(Command("check_energy"))
async def cmd_check_energy(callback_or_message: CallbackQuery | Message, state: FSMContext) -> None:
    await state.set_state(CheckEnergyStates.waiting_for_address)

    text = pad_message(
        "🔍 <b>ПРОВЕРКА ЭНЕРГИИ</b>\n\n"
        "Отправь Tron адрес для проверки баланса энергии:"
    )

    if isinstance(callback_or_message, CallbackQuery):
        await callback_or_message.message.edit_text(
            text, parse_mode="HTML", reply_markup=get_back_keyboard()
        )
        await callback_or_message.answer()
    else:
        await callback_or_message.answer(text, parse_mode="HTML", reply_markup=get_back_keyboard())


@router.message(CheckEnergyStates.waiting_for_address)
async def process_check_address(message: Message, state: FSMContext) -> None:
    address = message.text.strip()
    tron_service = TronService()

    if not tron_service.validate_address(address):
        await message.answer(
            pad_message("❌ <b>Неверный адрес</b>\n\nПопробуй ещё раз:"),
            parse_mode="HTML",
            reply_markup=get_back_keyboard(),
        )
        return

    await state.clear()
    balance = await tron_service.get_energy_balance(address)

    if "error" in balance:
        await message.answer(
            pad_message(f"❌ Ошибка: {balance['error']}"),
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)),
        )
        return

    energy_available = balance.get("energy_limit", 0) - balance.get("energy", 0)
    trx_balance = balance.get("balance", 0) / 1_000_000

    await message.answer(
        pad_message(
            f"📊 <b>БАЛАНС ЭНЕРГИИ</b>\n\n"
            f"📍 Адрес: <code>{address[:12]}...{address[-6:]}</code>\n\n"
            f"├ ⚡ Энергия: <b>{energy_available:,}</b> / {balance.get('energy_limit', 0):,}\n"
            f"├ 🌐 Bandwidth: <b>{balance.get('free_net_limit', 0):,}</b>\n"
            f"└ 💰 TRX: <b>{trx_balance:.2f}</b>\n\n"
            f"💡 <b>Для перевода USDT нужно:</b>\n"
            f"├ ~70,000 энергии (кошелёк с USDT)\n"
            f"└ ~140,000 энергии (пустой кошелёк)"
        ),
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)),
    )
