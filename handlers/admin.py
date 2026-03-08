# ================================================================
# handlers/admin.py
# ================================================================
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from config import (SUPER_ADMIN_ID, AA_NAME, AA_PHONE, AA_TID, AA_RATE,
                    ABC_TYPE, ABC_MSG)
from keyboards import kb_admin, REMOVE
from db import (all_agents, agent_by_id, add_agent, set_agent_field,
                remove_agent, master_log, all_clients, all_apps, all_payments,
                make_agent_sheet, agent_by_tid, agent_status, trial_end_date,
                db, MASTER_SHEET)
from utils import user_data, now_ist, today_ist, month_ist, safe_float, safe_int, gen_agent_id, valid_phone, divider


def is_admin(tid: int) -> bool:
    return tid == SUPER_ADMIN_ID


# ── Admin home ────────────────────────────────────────────────
async def admin_home(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👑 Admin Panel", reply_markup=kb_admin())


# ── Add Agent ─────────────────────────────────────────────────
async def add_agent_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text("➕ *New Agent*\n\nStep 1/4 — Agent ka Naam:", parse_mode=ParseMode.MARKDOWN, reply_markup=REMOVE)
    return AA_NAME

async def aa_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    user_data(tid)["aa_name"] = update.message.text.strip()
    await update.message.reply_text(f"Naam: {user_data(tid)['aa_name']}\n\nStep 2/4 — Phone Number (10 digit):")
    return AA_PHONE

async def aa_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    phone = update.message.text.strip()
    if not valid_phone(phone):
        await update.message.reply_text("❌ 10 digit phone number daalo:")
        return AA_PHONE
    user_data(tid)["aa_phone"] = phone
    await update.message.reply_text(f"Phone: {phone}\n\nStep 3/4 — Agent ka Telegram ID:\n(@userinfobot se pata kar sakte hain)")
    return AA_TID

async def aa_tid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    raw = update.message.text.strip()
    if not raw.lstrip("-").isdigit():
        await update.message.reply_text("❌ Sirf number daalo (Telegram ID):")
        return AA_TID
    user_data(tid)["aa_tid"] = raw
    await update.message.reply_text(f"TID: {raw}\n\nStep 4/4 — Rate per App (Rs mein, sirf number):")
    return AA_RATE

async def aa_rate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid  = update.effective_user.id
    raw  = update.message.text.strip()
    try:
        rate = float(raw)
    except ValueError:
        await update.message.reply_text("❌ Sirf number daalo (jaise 50):")
        return AA_RATE

    d          = user_data(tid)
    agent_id   = gen_agent_id()
    agent_name = d["aa_name"]

    await update.message.reply_text("⏳ Agent sheet ban rahi hai... please wait.")

    # Create dedicated Google Sheet for this agent
    sheet_name = make_agent_sheet(agent_id, agent_name, rate)
    if not sheet_name:
        await update.message.reply_text(
            "❌ Sheet nahi ban paya. Google Drive API enable hai?\n"
            "Service account ko Drive API access chahiye.",
            reply_markup=kb_admin()
        )
        return ConversationHandler.END

    ok = add_agent({
        "agent_id":   agent_id,
        "agent_name": agent_name,
        "phone":      d["aa_phone"],
        "telegram_id":int(d["aa_tid"]),
        "sheet_name": sheet_name,
        "rate":       rate,
    })

    if not ok:
        await update.message.reply_text("❌ Agent save nahi hua. Dobara try karo.", reply_markup=kb_admin())
        return ConversationHandler.END

    te = trial_end_date()
    try:
        bot_me   = await ctx.bot.get_me()
        ref_link = f"https://t.me/{bot_me.username}?start=register_{agent_id}"
    except Exception:
        ref_link = "N/A"

    await update.message.reply_text(
        f"✅ *Agent Added!*\n\n"
        f"🆔 ID: `{agent_id}`\n"
        f"👤 Naam: {agent_name}\n"
        f"📱 Phone: {d['aa_phone']}\n"
        f"💰 Rate: Rs{rate}/app\n"
        f"📋 Sheet: `{sheet_name}`\n"
        f"⏳ Trial: 3 din ({te} tak)\n\n"
        f"🔗 Referral Link:\n{ref_link}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb_admin()
    )

    # Notify agent
    try:
        await ctx.bot.send_message(
            chat_id=int(d["aa_tid"]),
            text=f"🎉 Aapko *Faiz Online Service* mein Agent banaya gaya hai!\n\n"
                 f"🆔 Agent ID: `{agent_id}`\n"
                 f"💰 Rate: Rs{rate}/app\n"
                 f"⏳ Trial: {te} tak\n\n"
                 f"Bot start karne ke liye /start bhejiye.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass

    return ConversationHandler.END


# ── All Agents ────────────────────────────────────────────────
async def all_agents_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    agents = all_agents()
    if not agents:
        await update.message.reply_text("❌ Koi agent nahi.", reply_markup=kb_admin())
        return
    await update.message.reply_text(f"👥 *All Agents ({len(agents)})*", parse_mode=ParseMode.MARKDOWN)
    for a in agents:
        st = agent_status(a)
        icon = "✅" if st == "active" else "⏳" if st == "trial" else "🚫"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🗑 Remove", callback_data=f"REMOVE_AGENT|{a['agent_id']}"),
            InlineKeyboardButton("💰 Set Rate", callback_data=f"SET_RATE|{a['agent_id']}"),
        ]])
        try:
            await update.message.reply_text(
                f"{icon} *{a.get('agent_name')}*\n"
                f"🆔 `{a.get('agent_id')}`\n"
                f"📱 {a.get('phone')}  |  TID: `{a.get('telegram_id')}`\n"
                f"💰 Rate: Rs{a.get('rate_per_app')}/app\n"
                f"📋 Sheet: `{a.get('sheet_name')}`\n"
                f"📊 Apps: {a.get('total_apps',0)}  |  Clients: {a.get('total_clients',0)}\n"
                f"⏳ Status: {st}  |  Trial end: {a.get('trial_end','')}",
                parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception:
            pass
    await update.message.reply_text(divider(), reply_markup=kb_admin())


# ── Find Agent ────────────────────────────────────────────────
async def find_agent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = ctx.args
    if not args:
        await update.message.reply_text("Usage: /find_agent <agent_id or name>", reply_markup=kb_admin())
        return
    q = " ".join(args).lower()
    results = [a for a in all_agents()
               if q in a.get("agent_name","").lower() or q in a.get("agent_id","").lower()]
    if not results:
        await update.message.reply_text("❌ Agent nahi mila.", reply_markup=kb_admin())
        return
    for a in results:
        await update.message.reply_text(
            f"✅ *{a['agent_name']}*\n🆔 {a['agent_id']}\nSheet: {a['sheet_name']}",
            parse_mode=ParseMode.MARKDOWN, reply_markup=kb_admin())


# ── Admin Stats ───────────────────────────────────────────────
async def admin_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    agents  = all_agents()
    t_apps  = sum(safe_int(a.get("total_apps",0))    for a in agents)
    t_clts  = sum(safe_int(a.get("total_clients",0)) for a in agents)
    active  = sum(1 for a in agents if agent_status(a) in ("active","trial"))
    await update.message.reply_text(
        f"📊 *Admin Stats*\n{divider()}\n"
        f"👥 Total Agents: {len(agents)} ({active} active)\n"
        f"👤 Total Clients: {t_clts}\n"
        f"📋 Total Apps: {t_apps}\n"
        f"📅 Today: {today_ist()}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb_admin())


# ── Admin Broadcast ───────────────────────────────────────────
async def admin_bc_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📝 Text",  callback_data="ABC_TEXT"),
        InlineKeyboardButton("🖼 Image", callback_data="ABC_IMAGE"),
        InlineKeyboardButton("🎤 Voice", callback_data="ABC_VOICE"),
    ]])
    await update.message.reply_text("📢 Broadcast type chuniye:", reply_markup=kb)
    return ABC_TYPE

async def admin_bc_type_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    tid = q.from_user.id
    t   = q.data.replace("ABC_","").lower()
    user_data(tid)["abc_type"] = t
    await q.edit_message_text(f"Type: {t}\n\nAb apna message bhejiye:")
    return ABC_MSG

async def admin_bc_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid      = update.effective_user.id
    bc_type  = user_data(tid).get("abc_type","text")
    agents   = [a for a in all_agents() if agent_status(a) in ("active","trial")]
    sent = failed = 0
    for ag in agents:
        try:
            ag_tid = int(ag.get("telegram_id",0))
            if not ag_tid:
                continue
            if bc_type == "text":
                await ctx.bot.send_message(ag_tid, update.message.text)
            elif bc_type == "image" and update.message.photo:
                await ctx.bot.send_photo(ag_tid, update.message.photo[-1].file_id,
                                         caption=update.message.caption or "")
            elif bc_type == "voice" and update.message.voice:
                await ctx.bot.send_voice(ag_tid, update.message.voice.file_id)
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(
        f"📢 Broadcast done!\n✅ Sent: {sent}\n❌ Failed: {failed}",
        reply_markup=kb_admin())
    return ConversationHandler.END


# ── Aliases / missing functions ──────────────────────────────
async def dashboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await admin_stats(update, ctx)

async def all_apps_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    agents  = all_agents()
    total   = 0
    pending = 0
    done    = 0
    for ag in agents:
        for ap in all_apps(ag):
            total += 1
            if ap.get("status") == "PENDING":
                pending += 1
            elif ap.get("status") == "DONE":
                done += 1
    await update.message.reply_text(
        f"📋 *All Applications*\n{divider()}\n"
        f"📊 Total: {total}\n"
        f"⏳ Pending: {pending}\n"
        f"✅ Done: {done}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb_admin())

async def all_payments_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    agents  = all_agents()
    total   = 0
    pending = 0
    paid    = 0
    for ag in agents:
        for p in all_payments(ag):
            total += 1
            st = p.get("status","").upper()
            if st == "PENDING":
                pending += 1
            elif st == "PAID":
                paid += 1
    await update.message.reply_text(
        f"💰 *All Payments*\n{divider()}\n"
        f"📊 Total: {total}\n"
        f"⏳ Pending: {pending}\n"
        f"✅ Paid: {paid}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb_admin())

async def logs_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "📜 Logs FOS_Master sheet ke 'logs' tab mein hain.",
        reply_markup=kb_admin())

async def monthly_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    agents = all_agents()
    mon    = month_ist()
    t_apps = sum(safe_int(a.get("total_apps",0)) for a in agents)
    t_clts = sum(safe_int(a.get("total_clients",0)) for a in agents)
    await update.message.reply_text(
        f"📅 *Monthly Report — {mon}*\n{divider()}\n"
        f"👥 Agents: {len(agents)}\n"
        f"👤 Clients: {t_clts}\n"
        f"📋 Apps: {t_apps}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb_admin())
