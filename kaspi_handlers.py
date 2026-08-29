from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

from database import PLANS
from kaspi_pay import PLAN_NAMES  # PLAN_PRICES_KZT и create_payment подключим позже


async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "💎 *Adai — все функции включены*\n\n"
        "✅ Безлимит кампаний\n"
        "✅ AI генерация баннеров\n"
        "✅ AI таргетолог 24/7\n"
        "✅ Запуск рекламы в Facebook/Instagram\n"
        "✅ Ежедневный отчёт в Telegram\n"
        "✅ Аналитика и статистика\n\n"
        "Выберите период подписки:"
    )
    keyboard = [
        [InlineKeyboardButton("1 месяц — 30 000 ₸", callback_data="kaspi_pay_month_1")],
        [InlineKeyboardButton("2 месяца — 60 000 ₸", callback_data="kaspi_pay_month_2")],
        [InlineKeyboardButton("3 месяца — 90 000 ₸", callback_data="kaspi_pay_month_3")],
    ]
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await update.message.reply_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def handle_pay_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    plan = query.data.replace("kaspi_pay_", "")
    if plan not in PLANS:
        await query.edit_message_text("❌ Неверный период.")
        return

    plan_info = PLANS[plan]
    amount = plan_info["price_kzt"]

    keyboard = [
        [InlineKeyboardButton("💬 WhatsApp", url=f"https://wa.me/77079011192?text=Хочу%20подписку%20{plan_info['name']}%20%E2%80%94%20{amount:,}%20%E2%82%B8")],
        [InlineKeyboardButton("✈️ Telegram", url="https://t.me/ZhasulanZhanbirbaev")],
    ]

    await query.edit_message_text(
        f"✅ *Отличный выбор!*\n\n"
        f"Тариф: *{plan_info['name']}*\n"
        f"Сумма: *{amount:,} ₸*\n\n"
        f"Напишите нам — выставим счёт на Kaspi и активируем доступ:\n\n"
        f"📱 WhatsApp: +7 707 901 11 92\n"
        f"✈️ Telegram: @ZhasulanZhanbirbaev",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


def register_kaspi_handlers(application):
    application.add_handler(CallbackQueryHandler(handle_pay_callback, pattern=r"^kaspi_pay_"))
