# ================================================================
# handlers/registration.py — /start + Client Registration
# ================================================================

from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from config import SUPER_ADMIN_ID, REG_NAME, REG_PHONE
from keyboards import kb_admin, kb_agent, kb_client, REMOVE
from db import (agent_by_id, agent_by_tid, find_client, add_client,
                detect_role, agent_status, all_agents)
from utils import user_data, now_ist, gen_client_code, valid_phone, safe_float, divider


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid  = update.effective_user.id
    args = ctx.args or []

    # ── Referral link: /start register_AGT-XXXX ──
    if args and args[0].startswith("register_"):
        agent_id = args[0][9:]
        agent    = agent_by_id(agent_id)

        if not agent:
            await update.message.reply_text(
                "❌ *Link Invalid!*\nAgent se naya link maango.",
                parse_mode=ParseMode.MARKDOWN)
            return ConversationHandler.END

        st = agent_status(agent)
        if st in ("blocked", "deleted", "expired"):
            await update.message.reply_text(
                "🚫 *Agent active nahi hai.*\nAgent se contact karein.",
                parse_mode=ParseMode.MARKDOWN)
            return ConversationHandler.END

        if tid == SUPER_ADMIN_ID:
            await update.message.reply_text("❌ Admin register nahi ho sakta.")
            return ConversationHandler.END

        if agent_by_tid(tid):
            await update.message.reply_text("❌ Aap pehle se ek agent hain.")
            return ConversationHandler.END

        c, _ = find_client(tid)
        if c:
            await update.message.reply_text(
                f"✅ *Aap already registered hain!*\n\n"
                f"🆔 ID: `{c['client_code']}`\n"
                f"👤 Naam: {c['full_name']}",
                parse_mode=ParseMode.MARKDOWN, reply_markup=kb_client())
            return ConversationHandler.END

        user_data[tid] = {"agent": agent}
        await update.message.reply_text(
            f"🎉 *Faiz Online Service mein Swagat!*\n\n"
            f"👨‍💼 Agent: *{agent['agent_name']}*\n\n"
            f"✏️ Apna *Poora Naam* bhejiye:",
            parse_mode=ParseMode.MARKDOWN, reply_markup=REMOVE)
        return REG_NAME

    # ── Normal /start — show panel ──
    role = detect_role(tid)

    if role == "admin":
        await update.message.reply_text(
            f"🔐 *Super Admin Panel — FOS*\n\n"
            f"Assalamualaikum *Salman bhai!* 👋\n"
            f"{divider()}\n"
            f"✅ Bot Active | 🕐 {now_ist()}\n"
            f"{divider()}",
            parse_mode=ParseMode.MARKDOWN, reply_markup=kb_admin())

    elif role == "agent":
        ag = agent_by_tid(tid)
        st = agent_status(ag)
        if st in ("blocked", "deleted"):
            await update.message.reply_text(
                "🚫 *Aapka account block hai.*\nAdmin se contact karein.",
                parse_mode=ParseMode.MARKDOWN)
            return
        if st == "expired":
            await update.message.reply_text(
                "⏰ *Free Trial Khatam!*\nAdmin se plan activate karwayein.",
                parse_mode=ParseMode.MARKDOWN)
            return
        trial_line = (f"\n⏳ Free Trial: *{ag.get('trial_end','')}* tak"
                      if st == "trial" else "")
        await update.message.reply_text(
            f"👤 *Agent Panel*\n\n"
            f"Assalamualaikum *{ag['agent_name']}* bhai! 👋\n"
            f"{divider()}\n"
            f"🆔 ID: `{ag['agent_id']}`\n"
            f"💰 Rate: Rs{safe_float(ag.get('rate_per_app',0))}/app"
            f"{trial_line}\n"
            f"{divider()}",
            parse_mode=ParseMode.MARKDOWN, reply_markup=kb_agent())

    elif role == "client":
        c, ag = find_client(tid)
        if c.get("status") == "blocked":
            await update.message.reply_text("🚫 Aapka account block hai. Agent se contact karein.")
            return
        # Panel info (no keyboard in same msg — fixes Telegram Web bug)
        await update.message.reply_text(
            f"FOS Client Panel\n\n"
            f"Assalamualaikum {c['full_name']}!\n"
            f"Client ID: {c['client_code']}\n"
            f"Balance: Rs{safe_float(c.get('balance',0))}\n"
            f"Agent: {ag['agent_name']}")
        await update.message.reply_text("Apna panel:", reply_markup=kb_client())

    else:
        await update.message.reply_text(
            "🙏 *Faiz Online Service mein Swagat!*\n\n"
            "Aap registered nahi hain.\n"
            "Apne *Agent se Referral Link* maango aur register karein.",
            parse_mode=ParseMode.MARKDOWN)


async def reg_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid  = update.effective_user.id
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("❌ Naam bahut chhota hai. Poora naam likhein:")
        return REG_NAME
    user_data[tid]["full_name"] = name
    await update.message.reply_text(
        f"✅ Naam: *{name}*\n\n📱 Ab *10-digit Phone Number* bhejiye:",
        parse_mode=ParseMode.MARKDOWN)
    return REG_PHONE


async def reg_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    phone = update.message.text.strip()
    if not valid_phone(phone):
        await update.message.reply_text("❌ 10 digit phone number chahiye. Dobara bhejiye:")
        return REG_PHONE

    agent = user_data[tid]["agent"]
    code  = gen_client_code()
    ok    = add_client(agent, {
        "client_code": code,
        "full_name":   user_data[tid]["full_name"],
        "phone":       phone,
        "telegram_id": tid,
    })

    if not ok:
        await update.message.reply_text("❌ System error. /start se dobara karo.")
        return ConversationHandler.END

    # Info message (no keyboard — fixes Telegram Web bug)
    await update.message.reply_text(
        f"Registration Successful!\n\n"
        f"Client ID: {code}\n"
        f"Naam: {user_data[tid]['full_name']}\n"
        f"Phone: {phone}\n"
        f"Agent: {agent['agent_name']}\n"
        f"Rate: Rs{safe_float(agent.get('rate_per_app',0))}/app\n\n"
        f"Ab aap applications submit kar sakte hain!")
    # Keyboard in separate message
    await update.message.reply_text("Apna panel use karein:", reply_markup=kb_client())

    # Notify agent
    try:
        await ctx.bot.send_message(int(agent["telegram_id"]),
            f"🆕 *Naya Client Registered!*\n\n"
            f"👤 {user_data[tid]['full_name']}\n"
            f"🆔 `{code}`\n📱 {phone}",
            parse_mode=ParseMode.MARKDOWN)
    except Exception:
        pass

    # Notify admin
    try:
        await ctx.bot.send_message(SUPER_ADMIN_ID,
            f"🆕 *Naya Client*\n\nAgent: {agent['agent_name']}\n"
            f"Client: {user_data[tid]['full_name']} | `{code}`",
            parse_mode=ParseMode.MARKDOWN)
    except Exception:
        pass

    user_data.pop(tid, None)
    return ConversationHandler.END


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    user_data.pop(tid, None)
    role = detect_role(tid)
    kb   = kb_admin() if role=="admin" else (kb_agent() if role=="agent" else kb_client())
    await update.message.reply_text("❌ Cancel ho gaya.", reply_markup=kb)
    return ConversationHandler.END
