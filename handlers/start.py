from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from config import config
from database import async_session, User
from keyboards.main_menu import get_main_menu_keyboard
from utils.formatting import pad_message, is_admin

router = Router()

WELCOME_TEXT = pad_message("""🔥 <b>TRX ENERGY BOT</b>

Добро пожаловать! Я помогу тебе купить энергию TRON для переводов USDT TRC-20 без комиссии.

⚡ <b>Как это работает:</b>
├ Выбери пакет энергии
├ Укажи адрес кошелька
├ Оплати через LOLZ Market
└ Получи энергию мгновенно

💰 <b>Цены:</b>
├ ⚡ 70k — 100₽
└ ⚡ 140k — 200₽

💡 Энергия возвращается автоматически через 1 час.

Выбери действие:""")

HELP_TEXT = pad_message("""📖 <b>Справка по боту</b>

<b>Что такое энергия TRON?</b>
Энергия нужна для выполнения смарт-контрактов (переводы USDT). Без энергии комиссия ~6-13 TRX, с энергией — почти бесплатно.

<b>Пакеты энергии:</b>
├ ⚡ 70k | 100₽ — для перевода на кошелёк с USDT
└ ⚡ 140k | 200₽ — для перевода на пустой кошелёк

<b>Как купить:</b>
1. Нажми «⚡ Купить Energy»
2. Выбери пакет или автоопределение
3. Введи адрес кошелька-отправителя
4. Оплати через LOLZ Market
5. Вернись и нажми «Я оплатил»

<b>Возврат энергии:</b>
Энергия автоматически возвращается через 1 час.""")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
            )
            session.add(user)
            await session.commit()
        elif user.username != message.from_user.username:
            user.username = message.from_user.username
            await session.commit()

    await message.answer(
        WELCOME_TEXT,
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        HELP_TEXT,
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)),
    )


@router.message(Command("menu"))
@router.message(F.text == "📱 Меню")
async def cmd_menu(message: Message) -> None:
    await message.answer(
        pad_message("🔥 <b>ГЛАВНОЕ МЕНЮ</b>\n\nВыбери действие:"),
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)),
    )


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        pad_message("🔥 <b>ГЛАВНОЕ МЕНЮ</b>\n\nВыбери действие:"),
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin(callback.from_user.id)),
    )
    await callback.answer()


def get_rules_keyboard() -> InlineKeyboardMarkup:
    from keyboards.main_menu import pad_text, W_FULL
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pad_text("📋 Общие положения", W_FULL), callback_data="rules_general")],
            [InlineKeyboardButton(text=pad_text("✅ Права пользователя", W_FULL), callback_data="rules_allowed")],
            [InlineKeyboardButton(text=pad_text("❌ Запрещённые действия", W_FULL), callback_data="rules_forbidden")],
            [InlineKeyboardButton(text=pad_text("⚠️ Санкции и наказания", W_FULL), callback_data="rules_sanctions")],
            [InlineKeyboardButton(text=pad_text("💰 Финансовые условия", W_FULL), callback_data="rules_finance")],
            [InlineKeyboardButton(text=pad_text("🔒 Безопасность", W_FULL), callback_data="rules_security")],
            [InlineKeyboardButton(text=pad_text("📞 Поддержка и споры", W_FULL), callback_data="rules_support")],
            [InlineKeyboardButton(text=pad_text("◀️ Назад", W_FULL), callback_data="back_to_menu")],
        ]
    )


def get_rules_back_keyboard() -> InlineKeyboardMarkup:
    from keyboards.main_menu import pad_text, W_FULL
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pad_text("◀️ К разделам правил", W_FULL), callback_data="rules")],
            [InlineKeyboardButton(text=pad_text("🏠 В главное меню", W_FULL), callback_data="back_to_menu")],
        ]
    )


@router.callback_query(F.data == "rules")
async def show_rules(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        pad_message(
            "📜 <b>ПРАВИЛА ИСПОЛЬЗОВАНИЯ СЕРВИСА</b>\n\n"
            "Добро пожаловать в раздел правил TRX Energy Bot.\n\n"
            "Используя данный сервис, вы автоматически соглашаетесь "
            "со всеми изложенными ниже условиями и обязуетесь их соблюдать.\n\n"
            "⚡ Последнее обновление: Декабрь 2025\n\n"
            "Выберите раздел для ознакомления:"
        ),
        parse_mode="HTML",
        reply_markup=get_rules_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "rules_general")
async def rules_general(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        pad_message(
            "📋 <b>ОБЩИЕ ПОЛОЖЕНИЯ</b>\n\n"
            "<b>1.1. О сервисе</b>\n"
            "TRX Energy Bot — автоматизированный сервис для аренды "
            "энергии в сети TRON. Сервис позволяет совершать переводы "
            "USDT TRC-20 с минимальной комиссией за счёт делегирования "
            "ресурсов энергии на ваш кошелёк.\n\n"
            "<b>1.2. Термины и определения</b>\n"
            "├ <b>Энергия</b> — ресурс сети TRON для выполнения смарт-контрактов\n"
            "├ <b>Делегирование</b> — временная передача энергии на ваш адрес\n"
            "├ <b>Пользователь</b> — физическое лицо, использующее сервис\n"
            "├ <b>Администрация</b> — владельцы и операторы сервиса\n"
            "└ <b>Баланс</b> — внутренний счёт пользователя в рублях\n\n"
            "<b>1.3. Возрастные ограничения</b>\n"
            "Используя бота, вы подтверждаете все правила.\n\n"
            "<b>1.4. Юрисдикция</b>\n"
            "Пользователь самостоятельно несёт ответственность за "
            "соблюдение законодательства своей страны при использовании "
            "криптовалютных сервисов."
        ),
        parse_mode="HTML",
        reply_markup=get_rules_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "rules_allowed")
async def rules_allowed(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        pad_message(
            "✅ <b>ПРАВА ПОЛЬЗОВАТЕЛЯ</b>\n\n"
            "<b>2.1. Вы имеете право:</b>\n\n"
            "├ Приобретать энергию для личных переводов USDT TRC-20\n"
            "├ Использовать несколько кошельков для получения энергии\n"
            "├ Пополнять баланс доступными способами оплаты\n"
            "├ Проверять баланс энергии любых адресов TRON\n"
            "├ Просматривать историю своих операций\n"
            "├ Сохранять адреса кошельков в профиле\n"
            "├ Обращаться в поддержку по техническим вопросам\n"
            "├ Получать уведомления о статусе заказов\n"
            "└ Использовать автоопределение нужного пакета энергии\n\n"
            "<b>2.2. Гарантии сервиса:</b>\n\n"
            "├ Мгновенное делегирование после подтверждения оплаты\n"
            "├ Автоматический возврат энергии через 1 час\n"
            "├ Уведомление о завершении аренды\n"
            "├ Сохранность баланса на вашем счёте\n"
            "└ Конфиденциальность данных пользователя\n\n"
            "<b>2.3. Лимиты:</b>\n\n"
            "├ Минимальное пополнение: 50₽\n"
            "├ Максимальное пополнение: 100,000₽\n"
            "└ Количество заказов: без ограничений"
        ),
        parse_mode="HTML",
        reply_markup=get_rules_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "rules_forbidden")
async def rules_forbidden(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        pad_message(
            "❌ <b>ЗАПРЕЩЁННЫЕ ДЕЙСТВИЯ</b>\n\n"
            "<b>3.1. Категорически запрещено:</b>\n\n"
            "🚫 <b>Мошенничество и обман:</b>\n"
            "├ Использование сервиса для скама и фишинга\n"
            "├ Обман других пользователей с помощью энергии\n"
            "├ Создание фейковых платежей и чеков\n"
            "└ Любые схемы обмана с использованием сервиса\n\n"
            "🚫 <b>Финансовые нарушения:</b>\n"
            "├ Отмывание денежных средств (AML)\n"
            "├ Чарджбэки и оспаривание платежей\n"
            "├ Использование украденных платёжных данных\n"
            "└ Финансирование незаконной деятельности\n\n"
            "🚫 <b>Технические нарушения:</b>\n"
            "├ Попытки взлома или эксплуатации уязвимостей\n"
            "├ DDoS-атаки и спам запросами\n"
            "├ Использование ботов и автоматизации\n"
            "└ Реверс-инжиниринг сервиса\n\n"
            "🚫 <b>Прочие нарушения:</b>\n"
            "├ Передача/продажа аккаунта третьим лицам\n"
            "├ Мультиаккаунтинг для обхода банов\n"
            "├ Распространение ложной информации о сервисе\n"
            "└ Оскорбление администрации и пользователей"
        ),
        parse_mode="HTML",
        reply_markup=get_rules_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "rules_sanctions")
async def rules_sanctions(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        pad_message(
            "⚠️ <b>САНКЦИИ И НАКАЗАНИЯ</b>\n\n"
            "<b>4.1. Уровни нарушений:</b>\n\n"
            "🟡 <b>Лёгкие нарушения:</b>\n"
            "├ Флуд в поддержку\n"
            "├ Некорректное поведение\n"
            "├ Мелкий спам\n"
            "└ <i>Санкция: предупреждение</i>\n\n"
            "🟠 <b>Средние нарушения:</b>\n"
            "├ Повторные лёгкие нарушения\n"
            "├ Попытки обмана поддержки\n"
            "├ Злоупотребление функциями бота\n"
            "└ <i>Санкция: бан 24 часа — 7 дней</i>\n\n"
            "🔴 <b>Тяжёлые нарушения:</b>\n"
            "├ Мошенничество с использованием сервиса\n"
            "├ Чарджбэки и возвраты платежей\n"
            "├ Попытки взлома\n"
            "└ <i>Санкция: перманентный бан + обнуление баланса</i>\n\n"
            "⚫ <b>Критические нарушения:</b>\n"
            "├ Отмывание денег\n"
            "├ Финансирование терроризма\n"
            "├ Массовый скам с использованием сервиса\n"
            "└ <i>Санкция: бан + передача данных в органы</i>\n\n"
            "<b>4.2. Важно:</b>\n"
            "├ Решение о санкциях принимает администрация\n"
            "├ Бан может быть применён без предупреждения\n"
            "└ Обжалование возможно через поддержку"
        ),
        parse_mode="HTML",
        reply_markup=get_rules_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "rules_finance")
async def rules_finance(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        pad_message(
            "💰 <b>ФИНАНСОВЫЕ УСЛОВИЯ</b>\n\n"
            "<b>5.1. Оплата и пополнение:</b>\n\n"
            "├ Оплата производится через LOLZ Market\n"
            "├ Средства зачисляются мгновенно после оплаты\n"
            "├ Минимальная сумма пополнения: 50₽\n"
            "├ Максимальная сумма пополнения: 100,000₽\n"
            "└ Комиссия за пополнение: отсутствует\n\n"
            "<b>5.2. Цены на энергию:</b>\n\n"
            "├ 70,000 энергии — 100₽ (кошелёк с USDT)\n"
            "├ 140,000 энергии — 200₽ (пустой кошелёк)\n"
            "└ Цены могут изменяться без предупреждения\n\n"
            "<b>5.3. Возврат средств:</b>\n\n"
            "├ Возврат средств НЕ предусмотрен\n"
            "├ Баланс не подлежит выводу\n"
            "├ При бане баланс обнуляется\n"
            "└ Исключение: технический сбой по вине сервиса\n\n"
            "<b>5.4. Срок действия баланса:</b>\n\n"
            "├ Баланс бессрочный при активном аккаунте\n"
            "├ При неактивности 365+ дней — обнуление\n"
            "└ Предупреждение за 30 дней до обнуления\n\n"
            "<b>5.5. Налоги:</b>\n\n"
            "Пользователь самостоятельно несёт ответственность "
            "за уплату налогов согласно законодательству своей страны."
        ),
        parse_mode="HTML",
        reply_markup=get_rules_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "rules_security")
async def rules_security(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        pad_message(
            "🔒 <b>БЕЗОПАСНОСТЬ</b>\n\n"
            "<b>6.1. Защита аккаунта:</b>\n\n"
            "├ Аккаунт привязан к вашему Telegram ID\n"
            "├ Не передавайте доступ к Telegram третьим лицам\n"
            "├ Администрация никогда не просит пароли\n"
            "├ Остерегайтесь фишинговых ботов-клонов\n"
            "└ Официальный бот: @СЮДА ТЕГ БОТА\n\n"
            "<b>6.2. Безопасность кошельков:</b>\n\n"
            "├ Мы НЕ храним приватные ключи пользователей\n"
            "├ Мы НЕ имеем доступа к вашим средствам\n"
            "├ Энергия делегируется, а не переводится\n"
            "├ Проверяйте адрес перед покупкой энергии\n"
            "└ Ошибочный адрес = потеря средств\n\n"
            "<b>6.3. Конфиденциальность:</b>\n\n"
            "├ Мы храним: Telegram ID, username, адреса\n"
            "├ Мы НЕ передаём данные третьим лицам\n"
            "├ Исключение: запрос правоохранительных органов\n"
            "├ Логи операций хранятся 90 дней\n"
            "└ Вы можете запросить удаление данных\n\n"
            "<b>6.4. Ответственность:</b>\n\n"
            "Администрация не несёт ответственности за:\n"
            "├ Потерю средств из-за ошибки пользователя\n"
            "├ Действия третьих лиц с вашим аккаунтом\n"
            "├ Использование энергии в незаконных целях\n"
            "└ Сбои сети TRON и блокчейна"
        ),
        parse_mode="HTML",
        reply_markup=get_rules_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "rules_support")
async def rules_support(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        pad_message(
            "📞 <b>ПОДДЕРЖКА И СПОРЫ</b>\n\n"
            "<b>7.1. Обращение в поддержку:</b>\n\n"
            "├ Контакт: @ВАШ ТЕЛЕГРАМ\n"
            "├ Время ответа: до 24 часов\n"
            "├ Язык общения: русский, английский\n"
            "└ Режим работы: ежедневно\n\n"
            "<b>7.2. Что указать в обращении:</b>\n\n"
            "├ Ваш Telegram ID (есть в профиле)\n"
            "├ Номер заказа (ID МЕРЧАНТА)\n"
            "├ Подробное описание проблемы\n"
            "├ Скриншоты (если есть)\n"
            "└ Адрес кошелька (если связано с энергией)\n\n"
            "<b>7.3. Решение споров:</b>\n\n"
            "├ Все споры решаются в переписке с поддержкой\n"
            "├ Решение администрации является окончательным\n"
            "├ Угрозы и шантаж = мгновенный бан\n"
            "└ Публичные жалобы без обращения в ЛС игнорируются\n\n"
            "<b>7.4. Компенсации:</b>\n\n"
            "├ Компенсация возможна при сбое по вине сервиса\n"
            "├ Требуется подтверждение (TX hash, скрины)\n"
            "├ Срок рассмотрения: до 72 часов\n"
            "└ Форма компенсации: зачисление на баланс\n\n"
            "<b>7.5. Изменение правил:</b>\n\n"
            "Администрация оставляет за собой право изменять "
            "правила без предварительного уведомления. "
            "Актуальная версия всегда доступна в боте."
        ),
        parse_mode="HTML",
        reply_markup=get_rules_back_keyboard(),
    )
    await callback.answer()
