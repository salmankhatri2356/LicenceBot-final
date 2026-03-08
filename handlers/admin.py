# ================================================================
# handlers/admin.py — Super Admin Handlers
# Broadcast → sirf agents ko (3 types: Text/Image/Voice)
# ================================================================

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from config import SUPER_ADMIN_ID, TRIAL_DAYS, AA_NAME, AA_PHONE, AA_TID, AA_RATE, ABC_TYPE, ABC_MSG
from keyboards import kb_admin, REMOVE
from db import (all_agents, agent_by_id, add_agent, set_agent_field,
                remove_agent, master_log, all_clients, all_apps, all_payments,
                setup_agent_tabs, put_setting, agent_by_tid,
                agent_status, trial_end_date, db, MASTER_SHEET)
from utils import user_data, now_ist, today_ist, month_ist, safe_float, safe_int, gen_agent_id, valid_phone, divider

IST = ZoneInfo("Asia/Kolkata")


def is_admin(tid): return tid == SUPER_ADMIN_ID


# ── Dashboard ─────────────────────────────────────────────────
async def dashboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    agents  = all_agents()
    active  = sum(1 for a in agents if a.get("status") == "active")
    trial   = sum(1 for a in agents if a.get("status") == "trial")
    blocked = sum(1 for a in agents if a.get("status") in ("blocked","expired"))
    total_c = sum(len(all_clients(a)) for a in agents)
    today   = today_ist()
    t_done  = sum(1 for a in agents for ap in all_apps(a)
                  if ap.get("created_at","")[:10]==today and ap.get("status")=="DONE")
    t_pend  = sum(1 for a in agents for ap in all_apps(a)
                  if ap.get("created_at","")[:10]==today and ap.get("status")=="PENDING")
    await update.message.reply_text(
        f"FOS Dashboard\n\n"
        f"Total Agents: {len(agents)}\n"
        f"Active: {active}  Trial: {trial}  Blocked: {blocked}\n"
        f"Total Clients: {total_c}\n\n"
        f"Today Done: {t_done}  Pending: {t_pend}\n\n"
        f"Time: {now_ist()}",
        reply_markup=kb_admin())


# ── All Agents ─────────────────────────────────────────────────
async def all_agents_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    agents = all_agents()
    if not agents:
        await update.message.reply_text("Koi agent nahi.", reply_markup=kb_admin())
        return
    await update.message.reply_text(f"All Agents ({len(agents)}):")
    for a in agents:
        st   = agent_status(a)
        icon = {"active":"Active","trial":"Trial","blocked":"Blocked","expired":"Expired"}.get(st,"?")
        te   = f"  Trial: {a.get('trial_end','')}" if st == "trial" else ""
        kb   = InlineKeyboardMarkup([[
            InlineKeyboardButton("Block",    callback_data=f"AG_BLOCK|{a['agent_id']}"),
            InlineKeyboardButton("Activate", callback_data=f"AG_ACTIV|{a['agent_id']}"),
            InlineKeyboardButton("Delete",   callback_data=f"AG_DEL|{a['agent_id']}"),
        ]])
        try:
            await update.message.reply_text(
                f"{icon}: {a['agent_name']} | {a['agent_id']}\n"
                f"Phone: {a.get('phone','')}  Rate: Rs{safe_float(a.get('rate_per_app',0))}/app\n"
                f"Clients: {a.get('total_clients',0)}  Apps: {a.get('total_apps',0)}{te}",
                reply_markup=kb)
        except Exception: pass


# ── Add Agent ──────────────────────────────────────────────────
async def add_agent_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text(
        "Naya Agent Add\n\nStep 1/4 - Agent ka Poora Naam:\n(/cancel se wapas)",
        reply_markup=REMOVE)
    return AA_NAME

async def aa_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid  = update.effective_user.id
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("Naam bahut chhota. Dobara:")
        return AA_NAME
    user_data[tid] = {"name": name}
    await update.message.reply_text(f"Naam: {name}\n\nStep 2/4 - Phone Number (10 digit):")
    return AA_PHONE

async def aa_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    phone = update.message.text.strip()
    if not valid_phone(phone):
        await update.message.reply_text("10 digit phone chahiye. Dobara:")
        return AA_PHONE
    user_data[tid]["phone"] = phone
    await update.message.reply_text(
        f"Phone: {phone}\n\nStep 3/4 - Agent ka Telegram ID:\n"
        f"(@userinfobot se pata kar sakte hain)")
    return AA_TID

async def aa_tid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    txt = update.message.text.strip()
    if not txt.isdigit():
        await update.message.reply_text("Sirf numbers. Dobara:")
        return AA_TID
    atid = int(txt)
    if agent_by_tid(atid):
        await update.message.reply_text("Yeh ID already registered hai.")
        return AA_TID
    if atid == SUPER_ADMIN_ID:
        await update.message.reply_text("Admin ko agent nahi bana sakte.")
        return AA_TID
    user_data[tid]["agent_tid"] = atid
    await update.message.reply_text(f"TID: {atid}\n\nStep 4/4 - Rate per App (Rs mein, sirf number):")
    return AA_RATE

async def aa_rate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    try:
        rate = float(update.message.text.strip())
        if rate <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("Valid number daalo (e.g. 40). Dobara:")
        return AA_RATE

    d          = user_data.get(tid, {})
    agent_name = d["name"]
    agent_tid  = d["agent_tid"]
    aid        = gen_agent_id()

    await update.message.reply_text("Agent add ho raha hai... please wait.")

    ok = add_agent({"agent_id": aid, "agent_name": agent_name, "phone": d["phone"],
                    "telegram_id": agent_tid, "sheet_name": aid, "rate": rate})
    if not ok:
        await update.message.reply_text("Master sheet update nahi hui.", reply_markup=kb_admin())
        return ConversationHandler.END

    # Setup agent tabs in FOS_Master (no new sheet needed)
    setup_agent_tabs(aid, agent_name, rate)
    ag = {"agent_id": aid}
    put_setting(ag, "rate_per_app", str(rate))
    put_setting(ag, "agent_name",   agent_name)

    bot_me   = await ctx.bot.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start=register_{aid}"
    te        = trial_end_date()

    await update.message.reply_text(
        f"Agent Added!\n\nID: {aid}\nNaam: {agent_name}\nPhone: {d['phone']}\n"
        f"Rate: Rs{rate}/app\nTrial: {TRIAL_DAYS} din ({te} tak)\n\nReferral Link:\n{ref_link}",
        reply_markup=kb_admin())
    try:
        await ctx.bot.send_message(agent_tid,
            f"Faiz Online Service mein Swagat!\n\nAgent ID: {aid}\nNaam: {agent_name}\n"
            f"Rate: Rs{rate}/app\nTrial: {TRIAL_DAYS} din ({te} tak)\n\n"
            f"Referral Link:\n{ref_link}\n\n"
            f"1. /start dabao\n2. Settings se QR upload karo\n3. Link clients ko bhejo!")
    except Exception:
        await update.message.reply_text("Agent ko welcome msg nahi gaya (unhone bot start nahi kiya).")
    user_data.pop(tid, None)
    return ConversationHandler.END


# ── Find Agent ─────────────────────────────────────────────────
async def find_agent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.strip().split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /find_agent AGT-XXXX", reply_markup=kb_admin())
        return
    a = agent_by_id(parts[1].upper())
    if not a:
        await update.message.reply_text(f"Agent {parts[1]} nahi mila.")
        return
    bot_me   = await ctx.bot.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start=register_{a['agent_id']}"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Block",    callback_data=f"AG_BLOCK|{a['agent_id']}"),
        InlineKeyboardButton("Activate", callback_data=f"AG_ACTIV|{a['agent_id']}"),
        InlineKeyboardButton("Delete",   callback_data=f"AG_DEL|{a['agent_id']}"),
    ]])
    await update.message.reply_text(
        f"Agent Profile\n\nID: {a.get('agent_id')}\nNaam: {a.get('agent_name')}\n"
        f"Phone: {a.get('phone')}\nRate: Rs{safe_float(a.get('rate_per_app',0))}/app\n"
        f"Status: {agent_status(a)}\nTrial End: {a.get('trial_end','N/A')}\n"
        f"Clients: {a.get('total_clients',0)}  Apps: {a.get('total_apps',0)}\n\n"
        f"Referral:\n{ref_link}", reply_markup=kb)


# ── All Apps ───────────────────────────────────────────────────
async def all_apps_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    today = today_ist()
    msg   = f"Today Apps - {today}\n\n"
    total = 0
    for ag in all_agents():
        tap = [a for a in all_apps(ag) if a.get("created_at","")[:10] == today]
        if not tap: continue
        msg += f"--- {ag['agent_name']} ---\n"
        for ap in tap:
            ic   = "Done" if ap.get("status") == "DONE" else "Pending"
            msg += f"{ic}: {ap.get('app_id')} | {ap.get('app_no')} | {ap.get('client_code')}\n"
        total += len(tap)
        msg += "\n"
    msg += f"Total: {total}"
    await update.message.reply_text(msg, reply_markup=kb_admin())


# ── All Payments ───────────────────────────────────────────────
async def all_payments_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = "Recent Payments\n\n"
    for ag in all_agents():
        pays = [p for p in all_payments(ag) if p.get("status") in ("PAID","PENDING")][-5:]
        if not pays: continue
        msg += f"--- {ag['agent_name']} ---\n"
        for p in pays:
            ic   = "Paid" if p.get("status") == "PAID" else "Pending"
            msg += f"{ic}: {p.get('payment_id')} | {p.get('client_code')} | Rs{p.get('amount_paid')}\n"
        msg += "\n"
    await update.message.reply_text(msg or "Koi payment nahi.", reply_markup=kb_admin())


# ── Logs ───────────────────────────────────────────────────────
async def logs_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        sh = db.open(MASTER_SHEET)
        w  = db.ws(sh, "logs") if sh else None
        if not w:
            await update.message.reply_text("Logs nahi mile.", reply_markup=kb_admin())
            return
        rows    = w.get_all_values()
        last_20 = rows[-20:] if len(rows) > 20 else rows[1:]
        msg     = "Master Logs (Last 20)\n\n"
        for r in reversed(last_20):
            if len(r) >= 4:
                msg += f"{r[0]} | {r[1]} | {r[3][:16]}\n"
        await update.message.reply_text(msg, reply_markup=kb_admin())
    except Exception as e:
        await update.message.reply_text(f"Error: {e}", reply_markup=kb_admin())


# ── Monthly Report ─────────────────────────────────────────────
async def monthly_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    month = month_ist()
    msg   = f"Monthly Report - {month}\n\n"
    grand = 0
    for ag in all_agents():
        done = [a for a in all_apps(ag)
                if a.get("done_at","")[:7] == month and a.get("status") == "DONE"]
        if not done: continue
        rate  = safe_float(ag.get("rate_per_app",0))
        msg  += f"{ag['agent_name']}: {len(done)} apps | Rs{len(done)*rate}\n"
        grand += len(done)
    msg += f"\nGrand Total: {grand} apps"
    await update.message.reply_text(msg, reply_markup=kb_admin())


# ================================================================
#  ADMIN BROADCAST → sirf AGENTS ko (Text / Image / Voice)
# ================================================================

async def admin_bc_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Text",  callback_data="ABC_TEXT"),
        InlineKeyboardButton("Image", callback_data="ABC_IMAGE"),
        InlineKeyboardButton("Voice", callback_data="ABC_VOICE"),
    ]])
    await update.message.reply_text(
        "Broadcast to All Agents\n\nType choose karo:",
        reply_markup=kb)
    return ABC_TYPE


async def admin_bc_type_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    tid = q.from_user.id
    bc_type = q.data.replace("ABC_", "").lower()
    user_data[tid] = {"bc_type": bc_type}
    hints = {
        "text":  "Text message type karo:\n(/cancel se cancel karo)",
        "image": "Photo bhejo (caption optional):\n(/cancel se cancel karo)",
        "voice": "Voice message bhejo:\n(/cancel se cancel karo)",
    }
    await q.edit_message_text(hints.get(bc_type, "Content bhejo:"))
    return ABC_MSG


async def admin_bc_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid     = update.effective_user.id
    bc_type = user_data.get(tid, {}).get("bc_type", "text")
    agents  = [a for a in all_agents() if agent_status(a) in ("active","trial")]
    sent    = failed = 0

    for ag in agents:
        atid = safe_int(ag.get("telegram_id", 0))
        if not atid:
            failed += 1
            continue
        try:
            if bc_type == "text":
                await ctx.bot.send_message(atid, update.message.text)
            elif bc_type == "image" and update.message.photo:
                await ctx.bot.send_photo(atid, update.message.photo[-1].file_id,
                                         caption=update.message.caption or "")
            elif bc_type == "voice" and update.message.voice:
                await ctx.bot.send_voice(atid, update.message.voice.file_id)
            else:
                await ctx.bot.send_message(atid, update.message.text or "")
            sent += 1
        except Exception:
            failed += 1

    user_data.pop(tid, None)
    await update.message.reply_text(
        f"Broadcast Done!\n\nAgents ko bheja: {sent}\nFailed: {failed}",
        reply_markup=kb_admin())
    return ConversationHandler.END
