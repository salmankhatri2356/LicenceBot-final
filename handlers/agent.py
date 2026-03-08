# ================================================================
# handlers/agent.py — Agent Panel Handlers
# ================================================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from config import BC_TYPE, BC_MSG, UR_RATE
from keyboards import kb_agent, REMOVE
from db import (agent_by_tid, all_clients, all_apps, all_payments,
                client_by_code, set_agent_field, put_setting, get_setting,
                agent_status, agent_log)
from utils import user_data, now_ist, today_ist, safe_float, safe_int, divider


# ── Pending Apps ──────────────────────────────────────────────
async def pending_apps(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    apps  = [a for a in all_apps(agent) if a.get("status") == "PENDING"]

    if not apps:
        await update.message.reply_text("✅ Koi pending application nahi!", reply_markup=kb_agent())
        return

    await update.message.reply_text(f"📥 *Pending Apps: {len(apps)}*", parse_mode=ParseMode.MARKDOWN)
    for ap in apps[-20:]:
        c       = client_by_code(agent, ap.get("client_code",""))
        c_name  = c["full_name"] if c else "Unknown"
        c_phone = c["phone"]    if c else "N/A"
        c_tid   = c["telegram_id"] if c else 0

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Mark Done",
                callback_data=f"DONE|{ap['app_id']}|{ap['client_code']}|{c_tid}|{agent['agent_id']}")
        ]])
        try:
            await update.message.reply_text(
                f"📋 *App ID:* `{ap.get('app_id')}`\n"
                f"{divider()}\n"
                f"📄 App No: {ap.get('app_no')}\n"
                f"📅 DOB: {ap.get('dob')}\n"
                f"🔒 Password: `{ap.get('password')}`\n"
                f"{divider()}\n"
                f"👤 {c_name}  |  🆔 `{ap.get('client_code')}`\n"
                f"📱 {c_phone}\n"
                f"⏰ {ap.get('created_at','')[:16]}",
                parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception:
            pass


# ── Today Summary ─────────────────────────────────────────────
async def today_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    today = today_ist()
    apps  = all_apps(agent)
    t_apps = [a for a in apps if a.get("created_at","")[:10] == today]
    done   = [a for a in t_apps if a.get("status") == "DONE"]
    pend   = [a for a in t_apps if a.get("status") == "PENDING"]
    rate   = safe_float(agent.get("rate_per_app", 0))
    pays   = all_payments(agent)
    t_recv = sum(safe_float(p.get("amount_paid",0))
                 for p in pays if p.get("payment_date") == today and p.get("status") == "PAID")

    await update.message.reply_text(
        f"📊 *Today Summary — {today}*\n\n"
        f"{divider()}\n"
        f"✅ Done: {len(done)}\n"
        f"⏳ Pending: {len(pend)}\n"
        f"📋 Total Apps: {len(t_apps)}\n"
        f"{divider()}\n"
        f"💸 Balance Deducted: Rs{len(done)*rate}\n"
        f"💰 Payments Received: Rs{t_recv}\n"
        f"{divider()}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb_agent())


# ── Work History ──────────────────────────────────────────────
async def work_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    done  = [a for a in all_apps(agent) if a.get("status") == "DONE"][-20:]
    if not done:
        await update.message.reply_text("❌ Koi completed app nahi.", reply_markup=kb_agent())
        return
    msg = f"📜 *Work History (Last {len(done)})*\n\n"
    for ap in reversed(done):
        msg += f"✅ `{ap.get('app_id')}` | {ap.get('app_no')} | {ap.get('client_code')} | {ap.get('done_at','')[:10]}\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_agent())


# ── My Clients ────────────────────────────────────────────────
async def my_clients(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid    = update.effective_user.id
    agent  = agent_by_tid(tid)
    clients = all_clients(agent)

    if not clients:
        await update.message.reply_text("❌ Koi client nahi.", reply_markup=kb_agent())
        return

    await update.message.reply_text(f"👥 *My Clients ({len(clients)})*", parse_mode=ParseMode.MARKDOWN)
    for c in clients:
        icon = "✅" if c.get("status") == "active" else "🚫"
        kb   = InlineKeyboardMarkup([[
            InlineKeyboardButton("🚫 Block",   callback_data=f"C_BLOCK|{c['client_code']}|{agent['agent_id']}"),
            InlineKeyboardButton("✅ Unblock", callback_data=f"C_UNBLK|{c['client_code']}|{agent['agent_id']}"),
        ]])
        try:
            await update.message.reply_text(
                f"{icon} *{c.get('full_name')}*\n"
                f"🆔 `{c.get('client_code')}`\n"
                f"📱 {c.get('phone')}  |  💰 Rs{safe_float(c.get('balance',0))}\n"
                f"📋 Apps: {c.get('total_apps',0)}  |  Joined: {c.get('joined_at','')[:10]}",
                parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception:
            pass

    bot_me   = await ctx.bot.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start=register_{agent['agent_id']}"
    await update.message.reply_text(
        f"🔗 *Referral Link:*\n`{ref_link}`",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb_agent())


# ── My Stats ─────────────────────────────────────────────────
async def my_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid    = update.effective_user.id
    agent  = agent_by_tid(tid)
    clients = all_clients(agent)
    apps    = all_apps(agent)
    pays    = all_payments(agent)

    active_c  = sum(1 for c in clients if c.get("status") == "active")
    blocked_c = sum(1 for c in clients if c.get("status") == "blocked")
    tot_bal   = sum(safe_float(c.get("balance",0)) for c in clients)
    done_apps = sum(1 for a in apps if a.get("status") == "DONE")
    tot_recv  = sum(safe_float(p.get("amount_paid",0)) for p in pays if p.get("status") == "PAID")

    await update.message.reply_text(
        f"📈 *My Stats*\n\n"
        f"{divider()}\n"
        f"👥 Total Clients: {len(clients)}\n"
        f"   ✅ Active: {active_c}  🚫 Blocked: {blocked_c}\n"
        f"💳 Combined Balance: Rs{round(tot_bal,2)}\n"
        f"{divider()}\n"
        f"📋 Total Apps: {len(apps)}\n"
        f"   ✅ Done: {done_apps}  ⏳ Pending: {len(apps)-done_apps}\n"
        f"{divider()}\n"
        f"💵 Total Received: Rs{round(tot_recv,2)}\n"
        f"{divider()}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb_agent())


# ── Settings ──────────────────────────────────────────────────
async def settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    bot_me   = await ctx.bot.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start=register_{agent['agent_id']}"
    qr_ok    = "✅ Uploaded" if get_setting(agent, "qr_file_id") else "❌ Not Uploaded"
    st       = agent_status(agent)
    t_line   = f"\n⏳ Trial: {agent.get('trial_end','')} tak" if st == "trial" else ""

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Update Rate", callback_data="ST_RATE"),
         InlineKeyboardButton("📷 Upload QR",   callback_data="ST_QR")],
        [InlineKeyboardButton("🔗 Referral Link", callback_data="ST_LINK")],
    ])
    await update.message.reply_text(
        f"⚙️ *Settings*\n\n"
        f"{divider()}\n"
        f"🆔 ID: `{agent.get('agent_id')}`\n"
        f"👤 Naam: {agent.get('agent_name')}\n"
        f"💰 Rate: Rs{safe_float(agent.get('rate_per_app',0))}/app\n"
        f"📷 QR: {qr_ok}\n"
        f"✅ Status: {st}{t_line}\n"
        f"{divider()}\n"
        f"🔗 Link:\n`{ref_link}`",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


# ── Broadcast ─────────────────────────────────────────────────
async def broadcast_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    user_data[tid] = {"agent": agent}
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📝 Text",  callback_data="BC_TEXT"),
        InlineKeyboardButton("🖼️ Image", callback_data="BC_IMAGE"),
        InlineKeyboardButton("🎙️ Voice", callback_data="BC_VOICE"),
    ]])
    await update.message.reply_text("📢 *Broadcast Type:*", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    return BC_TYPE

async def bc_type_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    tid = q.from_user.id
    bct = q.data.replace("BC_","").lower()
    user_data[tid]["bc_type"] = bct
    hints = {"text":"📝 Message type karein:","image":"🖼️ Photo bhejiye:","voice":"🎙️ Voice bhejiye:"}
    await q.edit_message_text(hints.get(bct,"Content bhejiye:") + "\n\n(/cancel se cancel karo)")
    return BC_MSG

async def bc_content(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    if tid not in user_data: return ConversationHandler.END
    agent = user_data[tid]["agent"]
    bct   = user_data[tid].get("bc_type","text")
    sent  = failed = 0
    for c in all_clients(agent):
        if c.get("status") != "active": continue
        ctid = safe_int(c.get("telegram_id",0))
        if not ctid: failed += 1; continue
        try:
            if bct == "text":
                await ctx.bot.send_message(ctid, update.message.text, parse_mode=ParseMode.MARKDOWN)
            elif bct == "image" and update.message.photo:
                await ctx.bot.send_photo(ctid, update.message.photo[-1].file_id,
                                         caption=update.message.caption or "")
            elif bct == "voice" and update.message.voice:
                await ctx.bot.send_voice(ctid, update.message.voice.file_id)
            else:
                await ctx.bot.send_message(ctid, update.message.text or "")
            sent += 1
        except Exception:
            failed += 1
    agent_log(agent, "BROADCAST", agent["agent_name"], "agent", f"sent:{sent} failed:{failed}")
    await update.message.reply_text(
        f"📢 *Broadcast Done!*\n\n✅ Sent: {sent}\n❌ Failed: {failed}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb_agent())
    user_data.pop(tid, None)
    return ConversationHandler.END


# ── Update Rate ───────────────────────────────────────────────
async def rate_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    user_data[tid] = {"agent": agent}
    await update.message.reply_text(
        f"💰 Current Rate: *Rs{safe_float(agent.get('rate_per_app',0))}/app*\n\n"
        f"Naya rate bhejiye:\n(/cancel se cancel karo)",
        parse_mode=ParseMode.MARKDOWN, reply_markup=REMOVE)
    return UR_RATE

async def rate_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    try:
        rate = float(update.message.text.strip())
        if rate <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Valid number daalo. Dobara:")
        return UR_RATE
    agent = user_data[tid]["agent"]
    set_agent_field(agent["agent_id"], "rate_per_app", rate)
    put_setting(agent, "rate_per_app", str(rate))
    await update.message.reply_text(
        f"✅ *Rate Updated!*\nNaya Rate: Rs{rate}/app",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb_agent())
    user_data.pop(tid, None)
    return ConversationHandler.END


# ── QR Photo receive ──────────────────────────────────────────
async def qr_receive(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    tid = update.effective_user.id
    if not (user_data.get(tid,{}).get("awaiting_qr")):
        return False
    if not update.message.photo:
        await update.message.reply_text("❌ Sirf photo bhejiye.")
        return True
    fid   = update.message.photo[-1].file_id
    agent = user_data[tid]["agent"]
    put_setting(agent, "qr_file_id", fid)
    await update.message.reply_text("✅ *QR Uploaded!*\nAb clients QR dekh sakenge.", parse_mode=ParseMode.MARKDOWN, reply_markup=kb_agent())
    user_data.pop(tid, None)
    return True
