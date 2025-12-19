from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

EM_SPACE = "\u2003"
W_FULL = 24
W_HALF = 11


def pad_text(text: str, width: int = 24) -> str:
    text_len = len(text)
    if text_len >= width:
        return text
    padding = width - text_len
    left_pad = padding // 2
    right_pad = padding - left_pad
    return EM_SPACE * left_pad + text + EM_SPACE * right_pad


def get_main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=pad_text("⚡ Купить Energy", W_FULL), callback_data="buy_energy")],
        [InlineKeyboardButton(text=pad_text("💰 Пополнить баланс", W_FULL), callback_data="topup_balance")],
        [
            InlineKeyboardButton(text=pad_text("👤 Профиль", W_HALF), callback_data="profile"),
            InlineKeyboardButton(text=pad_text("📜 Правила", W_HALF), callback_data="rules"),
        ],
        [InlineKeyboardButton(text=pad_text("🔍 Проверить энергию", W_FULL), callback_data="check_energy")],
        [InlineKeyboardButton(text=pad_text("📋 История", W_FULL), callback_data="history")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton(text=pad_text("🔐 Админ-панель", W_FULL), callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_energy_packages_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=pad_text("⚡ 70k | 100₽", W_HALF), callback_data="energy_70k"),
                InlineKeyboardButton(text=pad_text("⚡ 140k | 200₽", W_HALF), callback_data="energy_140k"),
            ],
            [InlineKeyboardButton(text=pad_text("🔄 Автоопределение", W_FULL), callback_data="energy_auto")],
            [InlineKeyboardButton(text=pad_text("◀️ Назад", W_FULL), callback_data="back_to_menu")],
        ]
    )


def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pad_text("◀️ Назад", W_FULL), callback_data="back_to_menu")]
        ]
    )


def get_confirm_payment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pad_text("✅ Я оплатил", W_FULL), callback_data="check_payment")],
            [InlineKeyboardButton(text=pad_text("❌ Отмена", W_FULL), callback_data="cancel_order")],
        ]
    )


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pad_text("❌ Отмена", W_FULL), callback_data="cancel_order")]
        ]
    )


def get_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=pad_text("💰 Пополнить", W_HALF), callback_data="topup_balance"),
                InlineKeyboardButton(text=pad_text("📍 Адрес", W_HALF), callback_data="change_address"),
            ],
            [InlineKeyboardButton(text=pad_text("📞 Контакты", W_FULL), callback_data="contacts")],
            [InlineKeyboardButton(text=pad_text("◀️ Назад", W_FULL), callback_data="back_to_menu")],
        ]
    )


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Меню")]],
        resize_keyboard=True,
    )


def get_confirm_keyboard() -> InlineKeyboardMarkup:
    return get_confirm_payment_keyboard()


def get_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pad_text("📊 Статистика", W_FULL), callback_data="admin_stats")],
            [InlineKeyboardButton(text=pad_text("👥 Пользователи", W_FULL), callback_data="admin_users")],
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
