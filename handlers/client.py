# ================================================================
# handlers/client.py — Client Panel Handlers
# PAYMENT → AGENT (not admin)
# ================================================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from config import SUPER_ADMIN_ID, APP_NO, APP_DOB, APP_PASS
from keyboards import kb_client, REMOVE
from db import (find_client, all_apps, get_setting, get_balance,
                add_app, add_payment, deduct_balance, inc_client_apps,
                app_exists)
from utils import user_data, now_ist, today_ist, safe_float, safe_int, gen_app_id, gen_pay_id, valid_dob


# ================================================================
#  QR HELPER — shows QR + asks amount
# ================================================================

async def _qr_and_ask(tid: int, c: dict, ag: dict, ctx, header: str = ""):
    qr_fid = get_setting(ag, "qr_file_id")
    bal    = safe_float(c.get("balance", 0))
    rate   = safe_float(ag.get("rate_per_app", 0))
    text   = (
        f"{header}"
        f"Payment QR\n\n"
        f"Balance: Rs{bal}\n"
        f"Rate/App: Rs{rate}\n"
        f"Agent: {ag['agent_name']}\n\n"
        f"QR scan karo, phir neeche amount type karo."
    )
    if qr_fid:
        try:
            await ctx.bot.send_photo(tid, qr_fid, caption=text)
        except Exception:
            await ctx.bot.send_message(tid, text)
    else:
        await ctx.bot.send_message(tid, text + "\n\nAgent ne abhi QR upload nahi kiya.")
        await ctx.bot.send_message(tid, "Apna panel:", reply_markup=kb_client())
        return False

    user_data[tid] = {"client": c, "agent": ag, "awaiting_pay_amount": True}
    await ctx.bot.send_message(
        tid,
        "Kitna amount pay kiya? (sirf number, e.g. 400)\n(/cancel se cancel karo)",
        reply_markup=REMOVE)
    return True


# ================================================================
#  NEW APPLICATION
# ================================================================

async def new_app_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    c, ag = find_client(tid)
    if not c:
        await update.message.reply_text("Registered nahi hain.", reply_markup=kb_client())
        return ConversationHandler.END
    if c.get("status") == "blocked":
        await update.message.reply_text("Account block hai.", reply_markup=kb_client())
        return ConversationHandler.END

    rate = safe_float(ag.get("rate_per_app", 0))
    bal  = safe_float(c.get("balance", 0))

    if bal < rate:
        await _qr_and_ask(tid, c, ag, ctx,
            header=f"Balance Kam Hai! (Rs{bal})\nRate: Rs{rate}\n\nPehle recharge karo:\n\n")
        return ConversationHandler.END

    user_data[tid] = {"client": c, "agent": ag, "rate": rate}
    await update.message.reply_text(
        f"Naya Application\nBalance: Rs{bal} | Rate: Rs{rate}\n\n"
        f"Step 1/3 - Application Number:\n(/cancel se cancel karo)",
        reply_markup=REMOVE)
    return APP_NO


async def app_no(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    no  = update.message.text.strip()
    if not no:
        await update.message.reply_text("Empty nahi ho sakta:")
        return APP_NO
    if app_exists(user_data[tid]["agent"], no, user_data[tid]["client"]["client_code"]):
        await update.message.reply_text(f"{no} already exist karta hai! Dobara:")
        return APP_NO
    user_data[tid]["app_no"] = no
    await update.message.reply_text(f"App No: {no}\n\nStep 2/3 - DOB (DD/MM/YYYY):")
    return APP_DOB


async def app_dob(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    dob = update.message.text.strip()
    if not valid_dob(dob):
        await update.message.reply_text("Format galat. DD/MM/YYYY (e.g. 15/06/1995):")
        return APP_DOB
    user_data[tid]["dob"] = dob
    await update.message.reply_text(f"DOB: {dob}\n\nStep 3/3 - Password:")
    return APP_PASS


async def app_pass(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    pwd = update.message.text.strip()
    if not pwd:
        await update.message.reply_text("Password empty nahi. Dobara:")
        return APP_PASS

    c    = user_data[tid]["client"]
    ag   = user_data[tid]["agent"]
    rate = user_data[tid]["rate"]

    if get_balance(ag, c["client_code"]) < rate:
        await update.message.reply_text("Balance nahi raha. Recharge karo.")
        await update.message.reply_text("Apna panel:", reply_markup=kb_client())
        user_data.pop(tid, None)
        return ConversationHandler.END

    app_id = gen_app_id()
    if not add_app(ag, {"app_id": app_id, "app_no": user_data[tid]["app_no"],
                        "dob": user_data[tid]["dob"], "password": pwd,
                        "client_code": c["client_code"]}):
        await update.message.reply_text("System error. Dobara try karo.")
        await update.message.reply_text("Apna panel:", reply_markup=kb_client())
        user_data.pop(tid, None)
        return ConversationHandler.END

    inc_client_apps(ag, c["client_code"])
    await update.message.reply_text(
        f"Application Submitted!\n\n"
        f"App ID: {app_id}\nApp No: {user_data[tid]['app_no']}\n"
        f"DOB: {user_data[tid]['dob']}\nStatus: PENDING\n\n"
        f"Balance agent ke Done karne ke baad katega.")
    await update.message.reply_text("Apna panel:", reply_markup=kb_client())

    done_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Mark Done",
            callback_data=f"DONE|{app_id}|{c['client_code']}|{tid}|{ag['agent_id']}")
    ]])
    try:
        await ctx.bot.send_message(int(ag["telegram_id"]),
            f"Naya Application!\nApp ID: {app_id}\n"
            f"App No: {user_data[tid]['app_no']}\nDOB: {user_data[tid]['dob']}\n"
            f"Password: {pwd}\nClient: {c['full_name']} | {c['client_code']}\n"
            f"Phone: {c['phone']}", reply_markup=done_kb)
    except Exception: pass

    user_data.pop(tid, None)
    return ConversationHandler.END


# ================================================================
#  INFO SCREENS
# ================================================================

async def today_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    c, ag = find_client(tid)
    if not c: return
    today  = today_ist()
    apps   = [a for a in all_apps(ag) if a.get("client_code") == c["client_code"]]
    t_apps = [a for a in apps if a.get("created_at", "")[:10] == today]
    done   = sum(1 for a in t_apps if a.get("status") == "DONE")
    rate   = safe_float(ag.get("rate_per_app", 0))
    msg    = f"Today {today}\nDone: {done}  Pending: {len(t_apps)-done}\nUsed: Rs{done*rate}\n\n"
    for ap in t_apps:
        msg += f"{'Done' if ap.get('status')=='DONE' else 'Pending'}: {ap.get('app_id')} | {ap.get('app_no')}\n"
    await update.message.reply_text(msg)
    await update.message.reply_text("Apna panel:", reply_markup=kb_client())


async def my_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    c, ag = find_client(tid)
    if not c: return
    apps  = [a for a in all_apps(ag) if a.get("client_code") == c["client_code"]]
    done  = sum(1 for a in apps if a.get("status") == "DONE")
    msg   = f"My History\nTotal: {len(apps)}  Done: {done}  Pending: {len(apps)-done}\n\n"
    for ap in reversed(apps[-15:]):
        msg += f"{'Done' if ap.get('status')=='DONE' else 'Pending'}: {ap.get('app_id')} | {ap.get('app_no')} | {ap.get('created_at','')[:10]}\n"
    await update.message.reply_text(msg)
    await update.message.reply_text("Apna panel:", reply_markup=kb_client())


async def my_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    c, ag = find_client(tid)
    if not c: return
    bal  = safe_float(c.get("balance", 0))
    rate = safe_float(ag.get("rate_per_app", 0))
    apps = [a for a in all_apps(ag) if a.get("client_code") == c["client_code"]]
    done = sum(1 for a in apps if a.get("status") == "DONE")
    await update.message.reply_text(
        f"My Balance\n\nBalance: Rs{bal}\nRate/App: Rs{rate}\n"
        f"Submit kar sakta hoon: {int(bal//rate) if rate else 0} apps\n"
        f"Total Used: Rs{round(done*rate,2)}")
    await update.message.reply_text("Apna panel:", reply_markup=kb_client())


async def my_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    c, ag = find_client(tid)
    if not c: return
    apps = [a for a in all_apps(ag) if a.get("client_code") == c["client_code"]]
    done = sum(1 for a in apps if a.get("status") == "DONE")
    await update.message.reply_text(
        f"My Profile\n\nID: {c.get('client_code')}\nNaam: {c.get('full_name')}\n"
        f"Phone: {c.get('phone')}\nJoined: {c.get('joined_at','')[:10]}\n\n"
        f"Agent: {ag.get('agent_name')}\nRate: Rs{safe_float(ag.get('rate_per_app',0))}/app\n\n"
        f"Apps: {len(apps)}  Done: {done}\nBalance: Rs{safe_float(c.get('balance',0))}")
    await update.message.reply_text("Apna panel:", reply_markup=kb_client())


async def contact_agent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    c, ag = find_client(tid)
    if not c: return
    try:
        await ctx.bot.send_message(int(ag["telegram_id"]),
            f"Contact Request!\n{c['full_name']} ne contact kiya\n"
            f"Code: {c['client_code']}\nPhone: {c['phone']}")
        await update.message.reply_text(f"Agent {ag['agent_name']} ko message gaya!")
    except Exception:
        await update.message.reply_text("Message nahi gaya. Agent se directly contact karein.")
    await update.message.reply_text("Apna panel:", reply_markup=kb_client())


# ================================================================
#  PAY / GET QR — from keyboard
# ================================================================

async def pay_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    c, ag = find_client(tid)
    if not c:
        await update.message.reply_text("Registered nahi hain.", reply_markup=kb_client())
        return ConversationHandler.END
    if c.get("status") == "blocked":
        await update.message.reply_text("Account block hai.", reply_markup=kb_client())
        return ConversationHandler.END
    await _qr_and_ask(tid, c, ag, ctx)
    return ConversationHandler.END


# ================================================================
#  AMOUNT INPUT — called by message_router
# ================================================================

async def handle_pay_amount_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    tid = update.effective_user.id
    d   = user_data.get(tid, {})
    if not d.get("awaiting_pay_amount"):
        return False

    text = update.message.text.strip()
    if text.startswith("/"):
        user_data.pop(tid, None)
        await update.message.reply_text("Cancel ho gaya.", reply_markup=kb_client())
        return True

    try:
        amt = float(text)
        if amt <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("Valid amount daao (e.g. 400). Dobara:")
        return True

    c   = d["client"]
    ag  = d["agent"]
    pid = gen_pay_id()

    add_payment(ag, {"pay_id": pid, "client_code": c["client_code"], "amount": amt})

    # Client confirmation
    await update.message.reply_text(
        f"Payment Request Bheji!\n\nID: {pid}\nAmount: Rs{amt}\n\n"
        f"Agent approve kare ga to balance add ho ga.")
    await update.message.reply_text("Apna panel:", reply_markup=kb_client())

    # *** AGENT ko jaata hai — NOT admin ***
    appr_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Approve",
            callback_data=f"PAY_APR|{pid}|{tid}|{amt}|{c['client_code']}|{ag['agent_id']}"),
        InlineKeyboardButton("Reject",
            callback_data=f"PAY_REJ|{pid}|{tid}|{c['client_code']}|{ag['agent_id']}"),
    ]])
    try:
        await ctx.bot.send_message(int(ag["telegram_id"]),
            f"Payment Request!\n\n"
            f"Client: {c['full_name']} | {c['client_code']}\n"
            f"Phone: {c['phone']}\n"
            f"Amount: Rs{amt}\n"
            f"Current Balance: Rs{safe_float(c.get('balance', 0))}\n"
            f"Pay ID: {pid}",
            reply_markup=appr_kb)
    except Exception: pass

    user_data.pop(tid, None)
    return True


# Kept for compat
async def pay_amount(update, ctx): return await handle_pay_amount_input(update, ctx)
async def pay_confirm_cb(update, ctx): pass
