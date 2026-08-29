import os
import logging
import base64
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

from database import (
    create_user, get_user, has_access, is_trial_active,
    get_active_subscription, get_campaigns, get_ai_log,
    get_admin_stats, PLANS, save_fb_token, get_fb_token,
)
from launch_handler import build_launch_handler, build_launch_activate_handler
from kaspi_handlers import show_plans, register_kaspi_handlers

load_dotenv()
BOT_TOKEN       = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID        = int(os.getenv("OWNER_ID", "0"))
WEBAPP_URL      = os.getenv("WEBAPP_URL", "").strip()
# Состояния для /creative
CREATIVE_STATES = {}  # user_id -> {"photo": bytes}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _webapp_keyboard(user_id: int):
    if not WEBAPP_URL:
        return None
    url = f"{WEBAPP_URL}?user_id={user_id}"
    return InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Открыть Adai", web_app=WebAppInfo(url=url))]])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user(user.id, user.username or "", user.first_name or "")

    webapp_url = f"{WEBAPP_URL}?user_id={user.id}" if WEBAPP_URL else None

    # ── Экран 1: кто мы ──────────────────────────────────────────────────────
    intro = (
        f"👋 *{user.first_name}, привет!*\n\n"
        "Я — *Adai*, ваш персональный ИИ-маркетолог.\n\n"
        "Помогаю малому бизнесу в Казахстане запускать рекламу "
        "в Facebook и Instagram — быстро, дёшево и без таргетолога.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎨 *Генерация баннеров*\n"
        "3 профессиональных варианта под ваш бизнес за 30 секунд. "
        "Текст, дизайн, подпись к посту — всё включено.\n\n"
        "🚀 *Запуск рекламы*\n"
        "Подключаете Facebook Ads — я сам создаю кампанию, "
        "настраиваю аудиторию и запускаю. Никаких настроек вручную.\n\n"
        "📊 *Умный мониторинг*\n"
        "ИИ проверяет кампании каждые 6 часов: останавливает "
        "убыточные, масштабирует рабочие. Вы только получаете лиды.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "*Для кого:*\n"
        "Стоматологии · Автосервисы · Салоны красоты · Кофейни "
        "· Фитнес · Автосалоны · Онлайн-школы · Цветочные\n\n"
        "💰 *Тарифы:* от 30 000 ₸/мес\n"
        "🎁 *Вам активированы 10 бесплатных генераций баннеров*\n\n"
        "Нажмите кнопку ниже и начните прямо сейчас 👇"
    )

    buttons = []
    if webapp_url:
        buttons.append([InlineKeyboardButton("🚀 Открыть Adai", web_app=WebAppInfo(url=webapp_url))])
    buttons.append([
        InlineKeyboardButton("💎 Тарифы", callback_data="start_plans"),
        InlineKeyboardButton("📞 Поддержка", url="https://wa.me/77079011192"),
    ])
    kb = InlineKeyboardMarkup(buttons)

    await update.message.reply_text(intro, parse_mode="Markdown", reply_markup=kb)


async def cb_start_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Тарифы' из /start — показываем планы."""
    await update.callback_query.answer()
    await show_plans(update, context)


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

    base_url = os.getenv("BASE_URL", "https://adai-zkif.onrender.com").rstrip("/")
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


async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not WEBAPP_URL:
        await update.message.reply_text("❌ WEBAPP_URL не задан в .env")
        return
    try:
        from telegram import MenuButtonWebApp, WebAppInfo
        await context.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="📊 Открыть Adai",
                web_app=WebAppInfo(url=WEBAPP_URL),
            )
        )
        await update.message.reply_text(
            f"✅ Домен зарегистрирован!\n\nMenu button → {WEBAPP_URL}\n\nТеперь Mini App откроется без ошибки."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


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
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("token",     cmd_token))
    app.add_handler(CommandHandler("ailog",     cmd_ailog))
    app.add_handler(CommandHandler("admin",     cmd_admin))
    app.add_handler(CommandHandler("setup",     cmd_setup))
    app.add_handler(CommandHandler("sync",      cmd_sync))
    app.add_handler(CommandHandler("creative",  cmd_creative))
    app.add_handler(CommandHandler("subscribe", show_plans))
    register_kaspi_handlers(app)
    app.add_handler(CallbackQueryHandler(cb_start_plans, pattern="^start_plans$"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_creative_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_buttons))
    return app


if __name__ == "__main__":
    app = build_app()
    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)
