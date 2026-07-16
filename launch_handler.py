import os
import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)

import database as db
import fb_launcher as fb
from banner_composer import generate_creative_for_direction

log = logging.getLogger(__name__)

BASE_URL = os.environ.get("BASE_URL", "https://like-ai-production.up.railway.app").rstrip("/")

# ── States ────────────────────────────────────────────────────────────────────
LAUNCH_ASK_PAGE_ID       = 0
LAUNCH_CHOOSE_DIRECTION  = 1
LAUNCH_CHOOSE_CREATIVE   = 2
LAUNCH_WAIT_PHOTO        = 3
LAUNCH_CONFIRM_AD_TEXT   = 4
LAUNCH_CONFIRM_BUDGET    = 5
LAUNCH_WAIT_BUDGET_INPUT = 6
LAUNCH_FINAL_PREVIEW     = 7


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ik(*rows):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t, callback_data=d) for t, d in row]
        for row in rows
    ])


async def _show_directions_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Show direction list inline buttons. Returns True if no directions (caller → END)."""
    uid = update.effective_user.id
    dirs = db.get_directions(uid)
    chat_id = update.effective_chat.id

    if not dirs:
        await context.bot.send_message(
            chat_id,
            f"У тебя нет направлений.\n\nСоздай первое в дашборде: {BASE_URL}/app?user_id={uid}",
        )
        return True

    rows = [[(f"📁 {d['name']}", f"launch_dir:{d['id']}")] for d in dirs]
    rows.append([("❌ Отмена", "launch_cancel")])
    await context.bot.send_message(
        chat_id,
        "Выбери направление для запуска:",
        reply_markup=_ik(*rows),
    )
    return False


async def _ask_ad_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show ad text for confirmation, auto-generate if missing. Returns next state."""
    chat_id = update.effective_chat.id
    direction = context.user_data["launch"]["direction"]
    ad_text = (direction.get("ad_text") or "").strip()

    if not ad_text:
        await context.bot.send_message(chat_id, "Нет текста объявления — генерирую через AI…")
        try:
            strategy = await fb.generate_brief_strategy(direction)
            ad_texts = strategy.get("ad_texts", {})
            ad_text = (
                ad_texts.get("urgent")
                or ad_texts.get("emotional")
                or (list(ad_texts.values())[0] if ad_texts else "")
            )
            db.update_direction_ad_text(direction["id"], ad_text)
            direction["ad_text"] = ad_text
            context.user_data["launch"]["direction"] = direction
        except Exception as e:
            log.exception("generate_brief_strategy failed")
            await context.bot.send_message(chat_id, f"Ошибка генерации текста: {e}")
            context.user_data.pop("launch", None)
            return ConversationHandler.END

    context.user_data["launch"]["ad_text"] = ad_text
    preview = ad_text[:400] + ("…" if len(ad_text) > 400 else "")
    kb = _ik(
        [("✅ Использовать", "launch_txt:use")],
        [("🔄 Сгенерировать заново", "launch_txt:regen")],
        [("❌ Отмена", "launch_txt:cancel")],
    )
    await context.bot.send_message(
        chat_id,
        f"📝 *Текст объявления:*\n\n{preview}",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    return LAUNCH_CONFIRM_AD_TEXT


async def _show_final_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show summary before FB launch. Returns LAUNCH_FINAL_PREVIEW."""
    chat_id = update.effective_chat.id
    d = context.user_data["launch"]["direction"]
    budget = context.user_data["launch"]["daily_budget"]
    ad_text = context.user_data["launch"]["ad_text"]

    text = (
        f"📋 *Готов к запуску:*\n"
        f"• Направление: {d['name']}\n"
        f"• Ниша: {d.get('niche') or '—'}\n"
        f"• Гео: {d.get('geo') or 'Казахстан'}\n"
        f"• Возраст: {d.get('age_min') or 25}–{d.get('age_max') or 55}\n"
        f"• Пол: {d.get('gender') or 'все'}\n"
        f"• Бюджет: {budget:.0f} ₸/день\n"
        f"• WhatsApp: {d.get('whatsapp_number') or '—'}\n"
        f"• Статус после создания: PAUSED\n\n"
        f"*Текст:*\n{ad_text[:300]}{'…' if len(ad_text) > 300 else ''}"
    )
    kb = _ik(
        [("🚀 Создать в Facebook", "launch_go:create")],
        [("❌ Отмена", "launch_go:cancel")],
    )
    await context.bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    return LAUNCH_FINAL_PREVIEW


def _parse_fb_error(err: str) -> str:
    if "190" in err:
        return "❌ Токен Facebook истёк. Подключи заново через /token."
    if "100" in err:
        return f"❌ Не хватает данных для FB: {err}"
    if "200" in err:
        return "❌ Нет прав на FB-аккаунте. Проверь Business Manager."
    if "2635" in err:
        return "❌ Гео не распознан Facebook. Измени в направлении."
    return f"❌ Ошибка Facebook: {err}"


# ── Handlers ──────────────────────────────────────────────────────────────────

async def launch_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id

    if not db.has_access(uid):
        await update.effective_message.reply_text(
            "❌ Доступ закрыт. Оформи подписку через /pay."
        )
        return ConversationHandler.END

    fb_token = db.get_fb_token(uid)
    if not fb_token:
        await update.effective_message.reply_text(
            "❌ Facebook не подключён.\n\nСначала подключи через /token."
        )
        return ConversationHandler.END

    user = db.get_user(uid)

    if not user.get("fb_page_id"):
        await update.effective_message.reply_text("⏳ Загружаю твои Facebook-страницы…")
        try:
            pages = await asyncio.to_thread(fb.get_fb_pages, fb_token["access_token"])
        except Exception as e:
            await update.effective_message.reply_text(f"Ошибка получения страниц FB: {e}")
            return ConversationHandler.END

        if not pages:
            await update.effective_message.reply_text(
                "У твоего FB-аккаунта нет страниц.\n"
                "Создай Facebook Page в Business Manager и возвращайся."
            )
            return ConversationHandler.END

        rows = [[(p["name"], f"launch_page:{p['id']}")] for p in pages]
        rows.append([("❌ Отмена", "launch_cancel")])
        await update.effective_message.reply_text(
            "Выбери Facebook-страницу для рекламы:",
            reply_markup=_ik(*rows),
        )
        return LAUNCH_ASK_PAGE_ID

    no_dirs = await _show_directions_list(update, context)
    return ConversationHandler.END if no_dirs else LAUNCH_CHOOSE_DIRECTION


async def launch_page_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    page_id = q.data.split(":", 1)[1]
    db.save_user_page_id(update.effective_user.id, page_id)
    await q.edit_message_text(f"✅ Страница сохранена.")
    no_dirs = await _show_directions_list(update, context)
    return ConversationHandler.END if no_dirs else LAUNCH_CHOOSE_DIRECTION


async def launch_direction_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    dir_id = int(q.data.split(":", 1)[1])
    uid = update.effective_user.id
    direction = db.get_direction(dir_id, uid)

    if not direction:
        await q.edit_message_text("Направление не найдено.")
        return ConversationHandler.END

    missing = []
    if not direction.get("geo"):
        missing.append("гео")
    if not direction.get("whatsapp_number"):
        missing.append("WhatsApp-номер")
    if not direction.get("daily_budget") or float(direction["daily_budget"]) <= 0:
        missing.append("бюджет")

    if missing:
        await q.edit_message_text(
            f"⚠️ В направлении не хватает: *{', '.join(missing)}*.\n\n"
            f"Заполни в дашборде: {BASE_URL}/app?user_id={uid}",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    context.user_data["launch"] = {"direction": dict(direction)}

    creatives = db.get_direction_creatives(dir_id)
    rows = [[(f"📸 Креатив #{c['id']}", f"launch_cr:existing:{c['id']}")] for c in creatives]
    rows += [
        [("🎨 Сгенерировать через AI", "launch_cr:generate")],
        [("📤 Загрузить фото из галереи", "launch_cr:upload")],
        [("❌ Отмена", "launch_cr:cancel")],
    ]
    await q.edit_message_text(
        f"*{direction['name']}* выбрано.\n\nВыбери или создай креатив:",
        parse_mode="Markdown",
        reply_markup=_ik(*rows),
    )
    return LAUNCH_CHOOSE_CREATIVE


async def launch_creative_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")
    action = parts[1]
    uid = update.effective_user.id
    chat_id = update.effective_chat.id

    if action == "cancel":
        await q.edit_message_text("Отменено.")
        context.user_data.pop("launch", None)
        return ConversationHandler.END

    if action == "upload":
        await q.edit_message_text("📤 Пришли фото в чат одним сообщением.")
        return LAUNCH_WAIT_PHOTO

    direction = context.user_data["launch"]["direction"]
    fb_token = db.get_fb_token(uid)

    if action == "existing":
        cr_id = int(parts[2])
        creatives = db.get_direction_creatives(direction["id"])
        creative = next((c for c in creatives if c["id"] == cr_id), None)
        if not creative or not creative.get("fb_image_hash"):
            await q.edit_message_text("Креатив не найден или не загружен в FB.")
            return ConversationHandler.END
        context.user_data["launch"]["image_hash"] = creative["fb_image_hash"]
        await q.edit_message_text("✅ Креатив выбран.")
        return await _ask_ad_text(update, context)

    if action == "generate":
        await q.edit_message_text("🎨 Генерирую баннер… (~10 сек)")
        try:
            image_bytes = await asyncio.to_thread(generate_creative_for_direction, direction)
            image_hash = await asyncio.to_thread(
                fb.upload_image_to_fb,
                fb_token["access_token"], fb_token["ad_account_id"],
                image_bytes, f"dir_{direction['id']}_ai.jpg",
            )
            db.add_direction_creative(
                direction["id"], f"ai_{direction['id']}.jpg", image_hash, None, "image"
            )
            context.user_data["launch"]["image_hash"] = image_hash
            await context.bot.send_message(chat_id, "✅ Баннер создан и загружен в FB.")
            return await _ask_ad_text(update, context)
        except Exception as e:
            log.exception("generate creative failed")
            await context.bot.send_message(chat_id, f"Ошибка генерации: {e}")
            context.user_data.pop("launch", None)
            return ConversationHandler.END

    return ConversationHandler.END


async def launch_wait_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.photo:
        await update.effective_message.reply_text("Это не фото. Пришли фото одним сообщением.")
        return LAUNCH_WAIT_PHOTO

    uid = update.effective_user.id
    photo = update.message.photo[-1]
    tg_file = await photo.get_file()
    image_bytes = bytes(await tg_file.download_as_bytearray())

    direction = context.user_data["launch"]["direction"]
    fb_token = db.get_fb_token(uid)

    try:
        image_hash = await asyncio.to_thread(
            fb.upload_image_to_fb,
            fb_token["access_token"], fb_token["ad_account_id"],
            image_bytes, f"dir_{direction['id']}_upload.jpg",
        )
        db.add_direction_creative(direction["id"], "user_upload.jpg", image_hash, None, "image")
        context.user_data["launch"]["image_hash"] = image_hash
        await update.message.reply_text("✅ Фото загружено в Facebook.")
        return await _ask_ad_text(update, context)
    except Exception as e:
        log.exception("upload photo failed")
        await update.message.reply_text(f"Ошибка загрузки в FB: {e}")
        context.user_data.pop("launch", None)
        return ConversationHandler.END


async def launch_ad_text_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    action = q.data.split(":")[1]
    chat_id = update.effective_chat.id

    if action == "cancel":
        await q.edit_message_text("Отменено.")
        context.user_data.pop("launch", None)
        return ConversationHandler.END

    if action == "regen":
        await q.edit_message_text("🔄 Генерирую новый вариант…")
        direction = context.user_data["launch"]["direction"]
        try:
            strategy = await fb.generate_brief_strategy(direction)
            ad_texts = strategy.get("ad_texts", {})
            new_text = (
                ad_texts.get("emotional")
                or ad_texts.get("urgent")
                or (list(ad_texts.values())[0] if ad_texts else "")
            )
            db.update_direction_ad_text(direction["id"], new_text)
            direction["ad_text"] = new_text
            context.user_data["launch"]["direction"] = direction
            context.user_data["launch"]["ad_text"] = new_text
        except Exception as e:
            await context.bot.send_message(chat_id, f"Ошибка генерации: {e}")
            return LAUNCH_CONFIRM_AD_TEXT

        kb = _ik(
            [("✅ Использовать", "launch_txt:use")],
            [("🔄 Сгенерировать заново", "launch_txt:regen")],
            [("❌ Отмена", "launch_txt:cancel")],
        )
        preview = new_text[:400] + ("…" if len(new_text) > 400 else "")
        await context.bot.send_message(
            chat_id,
            f"📝 *Новый текст:*\n\n{preview}",
            parse_mode="Markdown",
            reply_markup=kb,
        )
        return LAUNCH_CONFIRM_AD_TEXT

    # action == "use"
    direction = context.user_data["launch"]["direction"]
    budget = float(direction.get("daily_budget") or 5000)
    context.user_data["launch"]["daily_budget"] = budget
    kb = _ik(
        [("✅ Да", "launch_bud:yes")],
        [("✏️ Изменить", "launch_bud:edit")],
        [("❌ Отмена", "launch_bud:cancel")],
    )
    await q.edit_message_text(
        f"💰 Дневной бюджет: *{budget:.0f} ₸/день*. Запускать с этим?",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    return LAUNCH_CONFIRM_BUDGET


async def launch_budget_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    action = q.data.split(":")[1]

    if action == "cancel":
        await q.edit_message_text("Отменено.")
        context.user_data.pop("launch", None)
        return ConversationHandler.END

    if action == "edit":
        await q.edit_message_text("Введи бюджет числом (от 1 000 до 100 000):")
        return LAUNCH_WAIT_BUDGET_INPUT

    return await _show_final_preview(update, context)


async def launch_wait_budget_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        val = int(update.message.text.strip())
        assert 1000 <= val <= 100_000
    except (ValueError, AssertionError):
        await update.message.reply_text("Введи число от 1 000 до 100 000.")
        return LAUNCH_WAIT_BUDGET_INPUT

    context.user_data["launch"]["daily_budget"] = float(val)
    return await _show_final_preview(update, context)


async def launch_final_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    action = q.data.split(":")[1]

    if action == "cancel":
        await q.edit_message_text("Отменено.")
        context.user_data.pop("launch", None)
        return ConversationHandler.END

    await q.edit_message_text("⏳ Создаю кампанию в Facebook…")
    chat_id = update.effective_chat.id
    uid = update.effective_user.id

    d = context.user_data["launch"]["direction"]
    budget = context.user_data["launch"]["daily_budget"]
    ad_text = context.user_data["launch"]["ad_text"]
    image_hash = context.user_data["launch"]["image_hash"]

    fb_token = db.get_fb_token(uid)
    user = db.get_user(uid)

    try:
        campaign_id = await asyncio.to_thread(
            fb.create_fb_campaign,
            fb_token["access_token"], fb_token["ad_account_id"],
            f"AI-Launch / {d['name']}", "MESSAGES",
        )
        adset_id = await asyncio.to_thread(
            fb.create_fb_adset,
            fb_token["access_token"], fb_token["ad_account_id"], campaign_id,
            f"{d['name']} adset", float(budget), d.get("geo", "Казахстан"),
            int(d.get("age_min") or 25), int(d.get("age_max") or 55),
            d.get("gender", "all"), d.get("whatsapp_number", ""),
        )
        ad_id = await asyncio.to_thread(
            fb.create_fb_ad,
            fb_token["access_token"], fb_token["ad_account_id"], adset_id,
            f"{d['name']} ad", image_hash, ad_text,
            user["fb_page_id"], d.get("whatsapp_number", ""),
        )
        db.update_direction_campaign(d["id"], campaign_id, "created")

        account_num = fb_token["ad_account_id"].replace("act_", "")
        url = (
            f"https://business.facebook.com/adsmanager/manage/campaigns"
            f"?act={account_num}&selected_campaign_ids={campaign_id}"
        )
        msg = (
            f"✅ *Кампания создана (PAUSED)*\n\n"
            f"Campaign ID: `{campaign_id}`\n"
            f"AdSet ID: `{adset_id}`\n"
            f"Ad ID: `{ad_id}`\n\n"
            f"[Открыть в Ads Manager]({url})"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("▶️ Запустить (ACTIVE)", callback_data=f"launch_act:{campaign_id}"),
        ]])
        await context.bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=kb)

    except Exception as e:
        log.exception("FB campaign creation failed")
        await context.bot.send_message(chat_id, _parse_fb_error(str(e)))

    context.user_data.pop("launch", None)
    return ConversationHandler.END


async def launch_activate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Standalone handler (outside ConversationHandler) to activate a PAUSED campaign."""
    q = update.callback_query
    await q.answer()
    campaign_id = q.data.split(":", 1)[1]
    uid = update.effective_user.id
    fb_token = db.get_fb_token(uid)
    if not fb_token:
        await q.edit_message_text("FB-токен не найден.")
        return
    try:
        await asyncio.to_thread(fb.set_campaign_status, fb_token["access_token"], campaign_id, "ACTIVE")
        await q.edit_message_text(
            f"▶️ *Кампания запущена (ACTIVE)*\n\nID: `{campaign_id}`",
            parse_mode="Markdown",
        )
    except Exception as e:
        await q.edit_message_text(f"Ошибка запуска: {e}")


async def launch_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("launch", None)
    if update.message:
        await update.message.reply_text("Отменено.")
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Отменено.")
    return ConversationHandler.END


# ── Builders ──────────────────────────────────────────────────────────────────

def build_launch_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("launch", launch_entry),
            MessageHandler(filters.Regex("^🚀 Запустить кампанию$"), launch_entry),
        ],
        states={
            LAUNCH_ASK_PAGE_ID: [
                CallbackQueryHandler(launch_page_selected, pattern=r"^launch_page:"),
            ],
            LAUNCH_CHOOSE_DIRECTION: [
                CallbackQueryHandler(launch_direction_selected, pattern=r"^launch_dir:"),
            ],
            LAUNCH_CHOOSE_CREATIVE: [
                CallbackQueryHandler(launch_creative_selected, pattern=r"^launch_cr:"),
            ],
            LAUNCH_WAIT_PHOTO: [
                MessageHandler(filters.PHOTO, launch_wait_photo),
            ],
            LAUNCH_CONFIRM_AD_TEXT: [
                CallbackQueryHandler(launch_ad_text_selected, pattern=r"^launch_txt:"),
            ],
            LAUNCH_CONFIRM_BUDGET: [
                CallbackQueryHandler(launch_budget_selected, pattern=r"^launch_bud:"),
            ],
            LAUNCH_WAIT_BUDGET_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, launch_wait_budget_input),
            ],
            LAUNCH_FINAL_PREVIEW: [
                CallbackQueryHandler(launch_final_selected, pattern=r"^launch_go:"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", launch_cancel),
            CallbackQueryHandler(launch_cancel, pattern=r"^launch_cancel$"),
        ],
        per_message=False,
    )


def build_launch_activate_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(launch_activate, pattern=r"^launch_act:")
