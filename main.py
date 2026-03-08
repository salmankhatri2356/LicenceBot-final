# ================================================================
# main.py — FOS Bot Entry Point
# Run locally: python main.py
# Deploy: Railway.app (see Procfile)
# ================================================================

import logging
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters
)

from config import (BOT_TOKEN, SUPER_ADMIN_ID,
                    REG_NAME, REG_PHONE,
                    AA_NAME, AA_PHONE, AA_TID, AA_RATE,
                    APP_NO, APP_DOB, APP_PASS,
                    BC_TYPE, BC_MSG,
                    ABC_TYPE, ABC_MSG,
                    UR_RATE)
from db import db
from jobs import register_jobs

from handlers.registration import cmd_start, reg_name, reg_phone, cmd_cancel
from handlers.admin import (add_agent_start, aa_name, aa_phone, aa_tid, aa_rate,
                             find_agent, admin_bc_start, admin_bc_type_cb, admin_bc_send)
from handlers.agent import (broadcast_start, bc_type_cb, bc_content, rate_start, rate_save)
from handlers.client import new_app_start, app_no, app_dob, app_pass, pay_start
from handlers.callbacks import callback_router
from handlers.message_router import message_router, photo_router

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def post_init(app: Application):
    register_jobs(app)


def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # ── Registration / start ────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            REG_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_name)],
            REG_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_phone)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # ── Add Agent ────────────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^➕ Add Agent$"), add_agent_start)],
        states={
            AA_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, aa_name)],
            AA_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, aa_phone)],
            AA_TID:   [MessageHandler(filters.TEXT & ~filters.COMMAND, aa_tid)],
            AA_RATE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, aa_rate)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # ── New Application ─────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📋 New Application$"), new_app_start)],
        states={
            APP_NO:   [MessageHandler(filters.TEXT & ~filters.COMMAND, app_no)],
            APP_DOB:  [MessageHandler(filters.TEXT & ~filters.COMMAND, app_dob)],
            APP_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, app_pass)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # ── Agent Broadcast ─────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📢 Broadcast$"), broadcast_start)],
        states={
            BC_TYPE: [CallbackQueryHandler(bc_type_cb, pattern=r"^BC_")],
            BC_MSG:  [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bc_content),
                MessageHandler(filters.PHOTO, bc_content),
                MessageHandler(filters.VOICE, bc_content),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # ── Admin Broadcast (to Agents) ─────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📢 Broadcast All$"), admin_bc_start)],
        states={
            ABC_TYPE: [CallbackQueryHandler(admin_bc_type_cb, pattern=r"^ABC_")],
            ABC_MSG:  [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_bc_send),
                MessageHandler(filters.PHOTO, admin_bc_send),
                MessageHandler(filters.VOICE, admin_bc_send),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # ── Update Rate ─────────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^💰 Update Rate$"), rate_start)],
        states={UR_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, rate_save)]},
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # ── Commands ─────────────────────────────────────────────────
    app.add_handler(CommandHandler("find_agent", find_agent))
    app.add_handler(CommandHandler("cancel",     cmd_cancel))

    # ── Inline Buttons ───────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(callback_router))

    # ── Photos ───────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.PHOTO, photo_router))

    # ── All Text ─────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))

    return app


def main():
    if not BOT_TOKEN or "DAALO" in BOT_TOKEN:
        logger.error("BOT_TOKEN set nahi! config.py mein daalo.")
        return

    logger.info("Google Sheets connect ho raha hai...")
    if not db.connect():
        logger.error("Google Sheets connect nahi hua!")
        return

    logger.info("Bot start ho raha hai...")
    app = build_app()
    logger.info("FOS Bot chal raha hai!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()


# ================================================================
# /debug command — sirf admin use kar sakta hai
# Google Sheets live check karta hai
# ================================================================

from config import SUPER_ADMIN_ID as _ADMIN_ID

async def debug_cmd(update, context):
    if update.effective_user.id != _ADMIN_ID:
        return
    from db import db, MASTER_SHEET, all_agents
    lines = ["DEBUG REPORT\n"]

    # 1. Sheets connection
    try:
        sh = db.open(MASTER_SHEET)
        if sh:
            lines.append(f"Sheet: FOUND ({MASTER_SHEET})")
            ws = db.ws(sh, "agents")
            if ws:
                rows = ws.get_all_values()
                lines.append(f"agents tab: {len(rows)} rows (incl header)")
                if len(rows) > 1:
                    lines.append(f"Header: {rows[0]}")
                    lines.append(f"Row 1: {rows[1]}")
                else:
                    lines.append("agents tab EMPTY - koi data nahi!")
            else:
                lines.append("agents TAB NOT FOUND!")
        else:
            lines.append(f"Sheet NOT FOUND: {MASTER_SHEET}")
    except Exception as e:
        lines.append(f"Sheet ERROR: {e}")

    # 2. all_agents() result
    try:
        agents = all_agents()
        lines.append(f"\nall_agents() returned: {len(agents)} agents")
        for a in agents[:3]:
            lines.append(f"  - {a.get('agent_name')} | {a.get('agent_id')} | tid:{a.get('telegram_id')}")
    except Exception as e:
        lines.append(f"all_agents() ERROR: {e}")

    await update.message.reply_text("\n".join(lines))


# Patch into existing app — add debug handler
_original_build = build_app

def build_app():
    app = _original_build()
    app.add_handler(__import__('telegram.ext', fromlist=['CommandHandler']).CommandHandler("debug", debug_cmd))
    return app
