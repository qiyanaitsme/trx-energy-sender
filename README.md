<img width="1920" height="1080" alt="image" src="https://github.com/user-attachments/assets/abef0b80-f4e0-4024-b612-f9edc63df59b" />

# TRX Energy Bot

Телеграм-бот для продажи энергии TRON. Позволяет пользователям арендовать энергию для переводов USDT TRC-20 без комиссии.

## Возможности

- Продажа энергии TRON за рубли (LOLZ Market)
- Автоматическое делегирование энергии на кошелёк покупателя
- Автовозврат энергии через 1 час
- Внутренний баланс пользователей
- Rate limiting и защита от спама
- Защита от race condition при оплате
- Валидация платежей на сервере

## Пакеты энергии

| Пакет | Энергия | Цена | Назначение |
|-------|---------|------|------------|
| 70k   | 70,000  | 100₽ | Кошелёк с USDT |
| 140k  | 140,000 | 200₽ | Пустой кошелёк |

## Установка

```bash
cd trx-energy-bot
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

## Настройка
BOT_TOKEN=токен_от_BotFather
BOT_USERNAME=username_бота_без_собаки
ADMIN_IDS=123456789
TRON_PRIVATE_KEY=приватный_ключ_hex
TRON_WALLET_ADDRESS=TАдресКошелька
TRONGRID_API_KEY=ключ_trongrid
TRON_NETWORK=mainnet
LOLZ_API_TOKEN=токен_lolz
LOLZ_MERCHANT_ID=125
ENERGY_PACKAGE_70K=70000,100,Для кошелька с USDT
ENERGY_PACKAGE_140K=140000,200,Для пустого кошелька
ENERGY_RETURN_TIME=3600
MAX_PENDING_ORDERS=3
RATE_LIMIT_REQUESTS=30
RATE_LIMIT_WINDOW=60
SUPPORT_USERNAME=@твой_username

### Где взять ключи

| Ключ | Источник |
|------|----------|
| BOT_TOKEN | @BotFather |
| ADMIN_IDS | @userinfobot |
| TRON_PRIVATE_KEY | Экспорт из TronLink |
| TRONGRID_API_KEY | trongrid.io |
| LOLZ_API_TOKEN | Настройки LOLZ Market |

### Подготовка кошелька

1. Создай кошелёк в TronLink
2. Закинь TRX
3. Застейкай TRX → Energy (Stake 2.0)
4. Больше стейка = больше энергии для продажи

## Админ-панель

Доступна только для ADMIN_IDS:

- Статистика бота
- Список пользователей
- Баланс TRON кошелька
- Бан/разбан юзеров
- Изменение баланса

- Рассылка
