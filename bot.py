import os
import logging
import base64
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

from database import (
    create_user, get_user, has_access, is_trial_active,
    get_active_subscription, get_campaigns, get_ai_log,
    get_admin_stats, PLANS, save_fb_token, get_fb_token,
)
from launch_handler import build_launch_handler, build_launch_activate_handler

load_dotenv()
BOT_TOKEN       = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID        = int(os.getenv("OWNER_ID", "0"))
WEBAPP_URL      = os.getenv("WEBAPP_URL", "").strip()
# Состояния для /creative
CREATIVE_STATES = {}  # user_id -> {"photo": bytes}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _main_keyboard(user_id: int):
    inline_buttons = []
    if WEBAPP_URL:
        inline_buttons.append([InlineKeyboardButton("📊 Открыть кабинет", web_app=WebAppInfo(url=WEBAPP_URL))])
    inline_buttons.append([
        InlineKeyboardButton("🤖 Лог ИИ", callback_data="open_ailog"),
    ])
    return InlineKeyboardMarkup(inline_buttons)


def _reply_keyboard():
    buttons = [
        [KeyboardButton("🚀 Запустить кампанию")],
        [KeyboardButton("🎨 Креатив"), KeyboardButton("🤖 Лог ИИ")],
        [KeyboardButton("🔗 Facebook"), KeyboardButton("🔄 Синхронизация")],
        [KeyboardButton("📊 Статус")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, persistent=True)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = get_user(user.id) is None
    create_user(user.id, user.username or "", user.first_name or "")

    if is_new:
        base_url = os.getenv("BASE_URL", "https://like-ai-production.up.railway.app").rstrip("/")
        text = (
            f"👋 Привет, *{user.first_name}*!\n\n"
            "Добро пожаловать в *Adai* — ИИ-таргетолог для рекламы в Facebook и Instagram.\n\n"
            "🎁 *Пробный период активирован* — все функции открыты прямо сейчас.\n\n"
            "Чтобы запустить первую кампанию за 5 минут:\n\n"
            "1️⃣ Подключи рекламный кабинет Facebook → /token\n"
            "2️⃣ Создай направление (бриф бизнеса) в дашборде\n"
            "3️⃣ Запусти кампанию — ИИ возьмёт всё под контроль\n\n"
            "Отчёты каждое утро в 9:00. ИИ паузирует плохие кампании и масштабирует хорошие."
        )
        base_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔗 Подключить Facebook", url=f"{base_url}/fb/connect?user_id={user.id}"),
        ]])
    else:
        if is_trial_active(user.id):
            status = "🟡 Пробный период активен"
        else:
            sub = get_active_subscription(user.id)
            if sub:
                plan_name = PLANS.get(sub["plan"], {}).get("name", sub["plan"])
                expires = sub["expires_at"][:10]
                status = f"🟢 Подписка: {plan_name} (до {expires})"
            else:
                status = "🔴 Подписка истекла"

        fb = get_fb_token(user.id)
        fb_status = f"✅ `{fb['ad_account_id']}`" if fb else "❌ не подключён"

        text = (
            f"👋 С возвращением, *{user.first_name}*!\n\n"
            f"Статус: {status}\n"
            f"Facebook: {fb_status}\n\n"
            "🔗 /token — подключить Facebook Ads\n"
            "🔄 /sync — синхронизировать кампании\n"
            "🎨 /creative — сгенерировать рекламный креатив\n"
            "🤖 /ailog — решения ИИ\n"
        )

    kb = base_kb if is_new else _main_keyboard(user.id)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    await update.message.reply_text("Выберите действие:", reply_markup=_reply_keyboard())


async def cmd_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not has_access(user.id):
        await update.message.reply_text("❌ Доступ закрыт. Свяжитесь с администратором.")
        return

    args = context.args
    if args and len(args) >= 2:
        token, account_id = args[0], args[1]
        if not account_id.startswith("act_"):
            await update.message.reply_text("❌ ID должен начинаться с `act_`", parse_mode="Markdown")
            return
        save_fb_token(user.id, token, account_id)
        await update.message.reply_text("⏳ Подключаю и синхронизирую кампании...")
        from ai_manager import sync_fb_campaigns
        count = sync_fb_campaigns(user.id, token, account_id)
        sync_msg = f"\n📊 Синхронизировано кампаний: *{count}*" if count > 0 else "\n📊 Активных кампаний не найдено"
        await update.message.reply_text(
            f"✅ *Facebook подключён!*\n\nАккаунт: `{account_id}`{sync_msg}\n\nИИ начнёт мониторинг автоматически.",
            parse_mode="Markdown",
        )
        return

    base_url = os.getenv("BASE_URL", "https://like-ai-production.up.railway.app").rstrip("/")
    oauth_link = f"{base_url}/fb/connect?user_id={user.id}"
    existing = get_fb_token(user.id)
    if existing:
        text = (
            f"🔗 *Facebook подключён*\n\n"
            f"Аккаунт: `{existing['ad_account_id']}`\n"
            f"Дата: {existing['connected_at'][:10]}\n\n"
            f"Переподключить: [нажми здесь]({oauth_link})"
        )
    else:
        text = (
            "🔗 *Подключение Facebook Ads*\n\n"
            "Нажми кнопку ниже — авторизуйся через Facebook.\n"
            "Токен сохранится автоматически."
        )
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Подключить Facebook", url=oauth_link)]])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not has_access(user.id):
        await update.message.reply_text("❌ Доступ закрыт. Свяжитесь с администратором.")
        return
    fb = get_fb_token(user.id)
    if not fb:
        await update.message.reply_text("❌ Facebook не подключён.\n\nИспользуйте /token чтобы подключить.")
        return
    await update.message.reply_text("⏳ Синхронизирую кампании из Facebook...")
    from ai_manager import sync_fb_campaigns
    count = sync_fb_campaigns(user.id, fb["access_token"], fb["ad_account_id"])
    if count > 0:
        await update.message.reply_text(
            f"✅ Синхронизировано: *{count}* кампаний\n\nОткройте личный кабинет чтобы посмотреть.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("⚠️ Активных кампаний не найдено или ошибка токена.\n\nПроверьте токен через /token")


async def cmd_ailog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not has_access(user.id):
        await update.message.reply_text("❌ Нет доступа.")
        return

    log = get_ai_log(user.id, limit=10)
    if not log:
        await update.message.reply_text(
            "🤖 ИИ ещё не принимал решений.\n\nПервая проверка — через 6 часов после подключения /token."
        )
        return

    lines = ["🤖 *Последние решения ИИ:*\n"]
    for e in log:
        dt = e["created_at"][:16].replace("T", " ")
        scenario = f" [{e['scenario']}]" if e["scenario"] else ""
        lines.append(f"📅 `{dt}`{scenario}")
        lines.append(f"📁 {e['campaign_name']}")
        lines.append(f"➡️ {e['decision']}")
        if e["reason"]:
            lines.append(f"💬 _{e['reason']}_")
        lines.append("")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Доступ закрыт.")
        return

    s = get_admin_stats()
    await update.message.reply_text(
        "👑 *Панель администратора*\n\n"
        f"👥 Всего пользователей: *{s['total_users']}*\n"
        f"💳 Платящих: *{s['paying']}*\n"
        f"🆓 На триале: *{s['trial']}*\n"
        f"📊 Активных кампаний: *{s['campaigns']}*\n"
        f"💰 MRR: *{s['mrr']:,} ₸*",
        parse_mode="Markdown",
    )


async def handle_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "open_ailog":
        await cmd_ailog(update, context)


async def cmd_creative(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not has_access(user.id):
        await update.message.reply_text("❌ Доступ закрыт. Свяжитесь с администратором.")
        return
    await update.message.reply_text(
        "🎨 *Генератор рекламных креативов*\n\n"
        "Скиньте фото вашего товара или услуги — ИИ создаст 3 варианта рекламного баннера с текстами для поста.\n\n"
        "📸 Просто отправьте фото прямо сейчас.",
        parse_mode="Markdown",
    )


async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🎨 Креатив":
        await cmd_creative(update, context)
    elif text == "🤖 Лог ИИ":
        await cmd_ailog(update, context)
    elif text == "🔗 Facebook":
        await cmd_token(update, context)
    elif text == "🔄 Синхронизация":
        await cmd_sync(update, context)
    elif text == "📊 Статус":
        await cmd_start(update, context)
    else:
        await handle_creative_niche(update, context)


async def handle_creative_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not has_access(user.id):
        return

    import io
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    buf = io.BytesIO()
    await file.download_to_memory(buf)

    CREATIVE_STATES[user.id] = {"photo": buf.getvalue()}

    await update.message.reply_text(
        "✅ Фото получено!\n\n"
        "Теперь напишите нишу бизнеса:\n"
        "Например: *автозапчасти*, *салон красоты*, *кофейня*, *стоматология*, *барбершоп*",
        parse_mode="Markdown",
    )


async def handle_creative_niche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    state = CREATIVE_STATES.get(user.id)
    if not state or "photo" not in state:
        return

    if not has_access(user.id):
        await update.message.reply_text("❌ Доступ закрыт. Свяжитесь с администратором.")
        CREATIVE_STATES.pop(user.id, None)
        return

    niche = update.message.text.strip()
    photo_bytes = state["photo"]
    CREATIVE_STATES.pop(user.id, None)

    await update.message.reply_text("⏳ Генерирую баннеры... (займёт ~30 секунд)")

    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
        await update.message.reply_text("❌ OpenAI API не настроен.")
        return

    try:
        import io
        from image_generator import generate_ad_copy
        from banner_composer import create_banners
        from telegram import InputMediaPhoto

        photo_b64 = base64.b64encode(photo_bytes).decode()

        copy = await generate_ad_copy(niche, "", photo_b64)
        headlines = copy.get("headlines", [niche] * 3)
        bullets   = copy.get("bullets", [])
        cta       = copy.get("cta", "Узнать больше")

        banners = create_banners(photo_bytes, headlines, bullets, cta)

        media = []
        for i, b in enumerate(banners):
            img_data = base64.b64decode(b["image"].split(",")[1])
            buf = io.BytesIO(img_data)
            buf.name = f"banner_{i+1}.png"
            caption = b["label"] if i == 0 else ""
            media.append(InputMediaPhoto(media=buf, caption=caption))

        await update.message.reply_media_group(media=media)

        caption_text = (
            f"*Заголовки:*\n" +
            "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines)) +
            f"\n\n*CTA:* {cta}\n\n" +
            "\n".join(f"• {b}" for b in bullets)
        )
        await update.message.reply_text(caption_text, parse_mode="Markdown")

    except Exception as e:
        logger.error("Creative generation error: %s", e)
        await update.message.reply_text("❌ Ошибка генерации. Попробуйте позже.")


def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(build_launch_handler())
    app.add_handler(build_launch_activate_handler())
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("token",    cmd_token))
    app.add_handler(CommandHandler("ailog",    cmd_ailog))
    app.add_handler(CommandHandler("admin",    cmd_admin))
    app.add_handler(CommandHandler("sync",     cmd_sync))
    app.add_handler(CommandHandler("creative", cmd_creative))
    app.add_handler(CallbackQueryHandler(handle_inline, pattern=r"^open_"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_creative_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_buttons))
    return app


if __name__ == "__main__":
    app = build_app()
    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)
