# ================================================================
# jobs.py — Scheduled Background Jobs
# ================================================================

import logging
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import SUPER_ADMIN_ID, TRIAL_DAYS
from db import (all_agents, all_clients, all_apps, agent_status,
                set_agent_field, master_log, get_setting)
from utils import today_ist, safe_float, safe_int, divider

IST    = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger(__name__)


# ── Daily Summary (9 PM IST) ─────────────────────────────────
async def daily_summary(ctx: ContextTypes.DEFAULT_TYPE):
    today     = today_ist()
    agents    = all_agents()
    all_done  = 0

    for ag in agents:
        if agent_status(ag) not in ("active","trial"):
            continue
        try:
            apps    = all_apps(ag)
            t_apps  = [a for a in apps if a.get("created_at","")[:10] == today]
            done    = [a for a in t_apps if a.get("status") == "DONE"]
            pend    = [a for a in t_apps if a.get("status") == "PENDING"]
            rate    = safe_float(ag.get("rate_per_app",0))
            all_done += len(done)
            await ctx.bot.send_message(
                safe_int(ag["telegram_id"]),
                f"📊 *Daily Summary — {today}*\n\n"
                f"{divider()}\n"
                f"✅ Done: {len(done)}\n"
                f"⏳ Pending: {len(pend)}\n"
                f"💸 Deducted: Rs{len(done)*rate}\n"
                f"{divider()}\n"
                f"Kal phir milenge! 😊",
                parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.warning(f"daily_summary agent {ag.get('agent_id')}: {e}")

    try:
        await ctx.bot.send_message(SUPER_ADMIN_ID,
            f"📈 *Admin Daily Summary — {today}*\n\nTotal Done Today: *{all_done}*",
            parse_mode=ParseMode.MARKDOWN)
    except Exception:
        pass


# ── Low Balance Reminder (every 3 hours) ─────────────────────
async def low_balance_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    for ag in all_agents():
        if agent_status(ag) not in ("active","trial"):
            continue
        try:
            clients = all_clients(ag)
            apps    = all_apps(ag)
            for c in clients:
                if c.get("status") != "active":
                    continue
                if safe_float(c.get("balance",0)) > 0:
                    continue
                pend = [a for a in apps
                        if a.get("client_code") == c["client_code"]
                        and a.get("status") == "PENDING"]
                if not pend:
                    continue
                ctid = safe_int(c.get("telegram_id",0))
                if not ctid:
                    continue
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Pay / QR", callback_data="GET_QR")]])
                try:
                    await ctx.bot.send_message(ctid,
                        f"⚠️ *Balance Khatam!*\n\n"
                        f"Aapke {len(pend)} pending app(s) hain.\n"
                        f"Recharge karein taaki kaam ho sake!",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"low_balance_reminder agent {ag.get('agent_id')}: {e}")


# ── Trial Expiry Check (every 1 hour) ────────────────────────
async def trial_expiry_check(ctx: ContextTypes.DEFAULT_TYPE):
    for ag in all_agents():
        if ag.get("status") != "trial":
            continue
        st = agent_status(ag)
        if st == "expired":
            set_agent_field(ag["agent_id"], "status", "expired")
            master_log("TRIAL_EXPIRED", ag["agent_name"], ag["agent_id"])
            try:
                await ctx.bot.send_message(
                    safe_int(ag["telegram_id"]),
                    f"⏰ *Free Trial Khatam Ho Gaya!*\n\n"
                    f"Aapka {TRIAL_DAYS}-day free trial expire ho gaya.\n"
                    f"Admin se contact karein plan activate karne ke liye.",
                    parse_mode=ParseMode.MARKDOWN)
            except Exception:
                pass
            try:
                await ctx.bot.send_message(SUPER_ADMIN_ID,
                    f"⏰ *Trial Expired*\n\nAgent: {ag['agent_name']}\nID: `{ag['agent_id']}`",
                    parse_mode=ParseMode.MARKDOWN)
            except Exception:
                pass


# ── Register jobs ─────────────────────────────────────────────
def register_jobs(app):
    jq = app.job_queue
    jq.run_daily(daily_summary,        time=dtime(hour=21, minute=0, tzinfo=IST), name="daily_summary")
    jq.run_repeating(low_balance_reminder, interval=10800, first=60,   name="low_bal")
    jq.run_repeating(trial_expiry_check,   interval=3600,  first=30,   name="trial_check")
    logger.info("✅ Jobs registered")
