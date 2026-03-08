# ================================================================
# handlers/message_router.py — Routes All Incoming Text Messages
# ================================================================

from telegram import Update
from telegram.ext import ContextTypes

from db import detect_role, agent_by_tid, find_client, agent_status
from keyboards import kb_admin, kb_agent, kb_client
from utils import user_data, safe_float

# Admin handlers
from handlers.admin import (dashboard, all_agents_cmd, all_apps_cmd,
                             all_payments_cmd, logs_cmd, monthly_report)
# Agent handlers
from handlers.agent import (pending_apps, today_summary as agent_today,
                             work_history, my_clients, my_stats, settings)
# Client handlers
from handlers.client import (today_summary as client_today, my_history,
                              my_balance, my_profile, contact_agent,
                              handle_pay_amount_input)


async def photo_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle photo uploads — QR upload for agents."""
    from handlers.agent import qr_receive
    await qr_receive(update, ctx)


async def message_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    tid  = update.effective_user.id
    text = update.message.text.strip()
    d    = user_data.get(tid, {})

    # ── 1. Awaiting payment amount (from QR flow) ─────────────
    if d.get("awaiting_pay_amount"):
        await handle_pay_amount_input(update, ctx)
        return

    # ── 2. Awaiting rate update (from settings button) ────────
    if d.get("awaiting_rate"):
        try:
            rate = float(text)
            if rate <= 0:
                raise ValueError
            from db import set_agent_field, put_setting
            agent = d["agent"]
            set_agent_field(agent["agent_id"], "rate_per_app", rate)
            put_setting(agent, "rate_per_app", str(rate))
            user_data.pop(tid, None)
            await update.message.reply_text(
                f"Rate updated! Naya Rate: Rs{rate}/app",
                reply_markup=kb_agent())
        except ValueError:
            await update.message.reply_text("Valid number daalo (e.g. 50):")
        return

    # ── 3. Role-based routing ──────────────────────────────────
    role = detect_role(tid)

    # ════════════════════════════════════════
    #  ADMIN
    # ════════════════════════════════════════
    if role == "admin":
        routes = {
            "📊 Dashboard":      dashboard,
            "👥 All Agents":     all_agents_cmd,
            "📋 All Apps":       all_apps_cmd,
            "💰 All Payments":   all_payments_cmd,
            "🗂️ Logs":          logs_cmd,
            "📈 Monthly Report": monthly_report,
        }
        fn = routes.get(text)
        if fn:
            await fn(update, ctx)
        else:
            await update.message.reply_text("Neeche se button use karein:", reply_markup=kb_admin())

    # ════════════════════════════════════════
    #  AGENT
    # ════════════════════════════════════════
    elif role == "agent":
        agent = agent_by_tid(tid)
        st    = agent_status(agent)
        if st in ("blocked", "deleted"):
            await update.message.reply_text("Account block hai. Admin se contact karein.")
            return
        if st == "expired":
            await update.message.reply_text("Trial khatam. Admin se contact karein.")
            return

        if text == "🔄 Refresh":
            from handlers.registration import cmd_start
            await cmd_start(update, ctx)
            return

        routes = {
            "📥 Pending Apps":  pending_apps,
            "📊 Today Summary": agent_today,
            "📜 Work History":  work_history,
            "👥 My Clients":    my_clients,
            "📈 My Stats":      my_stats,
            "⚙️ Settings":     settings,
        }
        fn = routes.get(text)
        if fn:
            await fn(update, ctx)
        else:
            await update.message.reply_text("Neeche se button use karein:", reply_markup=kb_agent())

    # ════════════════════════════════════════
    #  CLIENT
    # ════════════════════════════════════════
    elif role == "client":
        c, ag = find_client(tid)
        if c and c.get("status") == "blocked":
            await update.message.reply_text("Account block hai. Agent se contact karein.")
            return

        routes = {
            "📊 Today Summary": client_today,
            "📜 My History":    my_history,
            "💰 My Balance":    my_balance,
            "ℹ️ My Profile":   my_profile,
            "📞 Contact Agent": contact_agent,
        }
        fn = routes.get(text)
        if fn:
            await fn(update, ctx)
        else:
            # Unknown text from client — just show keyboard
            await update.message.reply_text("Apna panel:", reply_markup=kb_client())

    # ════════════════════════════════════════
    #  UNKNOWN
    # ════════════════════════════════════════
    else:
        await update.message.reply_text(
            "Aap registered nahi hain.\nAgent se referral link maango.")
