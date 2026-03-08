# ================================================================
# handlers/callbacks.py — All Inline Button Callbacks
# ================================================================

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import SUPER_ADMIN_ID, TRIAL_DAYS
from keyboards import kb_client, kb_agent, kb_admin, REMOVE
from db import (agent_by_id, agent_by_tid, find_client, client_by_code,
                mark_done, deduct_balance, get_balance, add_balance,
                approve_payment, reject_payment, set_client_field,
                set_agent_field, remove_agent, master_log, get_setting,
                put_setting, agent_status, trial_end_date, agent_log)
from utils import user_data, safe_float, safe_int, divider


async def callback_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    data = q.data
    tid  = q.from_user.id

    # ================================================================
    #  MARK APP DONE
    # ================================================================
    if data.startswith("DONE|"):
        parts = data.split("|")
        if len(parts) < 5:
            return
        app_id, c_code, c_tid_str, ag_id = parts[1], parts[2], parts[3], parts[4]
        agent = agent_by_id(ag_id)
        if not agent:
            await q.edit_message_text("Agent nahi mila.")
            return
        if str(tid) != str(agent.get("telegram_id", "")):
            await q.answer("Sirf agent mark kar sakta hai.", show_alert=True)
            return

        from db import app_by_id
        app = app_by_id(agent, app_id)
        if not app:
            await q.edit_message_text("App nahi mili.")
            return
        if app.get("status") == "DONE":
            await q.answer("Already DONE hai.", show_alert=True)
            return

        rate = safe_float(agent.get("rate_per_app", 0))
        if not deduct_balance(agent, c_code, rate):
            await q.answer("Balance insufficient - deduct nahi hua.", show_alert=True)
            return

        mark_done(agent, app_id)
        new_bal = get_balance(agent, c_code)

        await q.edit_message_text(
            f"App Done!\n\n"
            f"ID: {app_id}\n"
            f"Rs{rate} deducted\n"
            f"Client Balance: Rs{new_bal}")

        # Notify client — with keyboard so it never disappears
        try:
            await ctx.bot.send_message(
                int(c_tid_str),
                f"Application Complete!\n\n"
                f"App ID: {app_id}\n"
                f"Rs{rate} balance se kata\n"
                f"Bacha Balance: Rs{new_bal}")
            await ctx.bot.send_message(int(c_tid_str), "Apna panel:", reply_markup=kb_client())
        except Exception:
            pass

        try:
            await ctx.bot.send_message(
                SUPER_ADMIN_ID,
                f"App Done - Agent: {agent['agent_name']}\n{app_id} | Rs{rate}")
        except Exception:
            pass

    # ================================================================
    #  PAYMENT APPROVE
    # ================================================================
    elif data.startswith("PAY_APR|"):
        if tid != SUPER_ADMIN_ID:
            await q.answer("Sirf Admin approve kar sakta hai.", show_alert=True)
            return
        parts = data.split("|")
        if len(parts) < 6:
            return
        pay_id, c_tid_s, amt_s, c_code, ag_id = parts[1], parts[2], parts[3], parts[4], parts[5]
        agent = agent_by_id(ag_id)
        if not agent:
            await q.edit_message_text("Agent nahi mila.")
            return
        amt     = safe_float(amt_s)
        approve_payment(agent, pay_id, "Admin")
        add_balance(agent, c_code, amt)
        new_bal = get_balance(agent, c_code)

        # Edit admin message to show approved
        await q.edit_message_text(
            f"Payment APPROVED!\n\n"
            f"ID: {pay_id}\n"
            f"Amount: Rs{amt}\n"
            f"Client Balance: Rs{new_bal}")

        # Client notification — ALWAYS send keyboard after
        try:
            await ctx.bot.send_message(
                int(c_tid_s),
                f"Payment Approved!\n\n"
                f"Rs{amt} aapke balance mein add ho gaya!\n"
                f"Naya Balance: Rs{new_bal}\n\n"
                f"Ab applications submit kar sakte hain.")
            # KEYBOARD HAMESHA BHEJNA HAI
            await ctx.bot.send_message(int(c_tid_s), "Apna panel:", reply_markup=kb_client())
        except Exception:
            pass

        # Agent notification
        try:
            await ctx.bot.send_message(
                safe_int(agent["telegram_id"]),
                f"Payment Approved\n{c_code} | Rs{amt} | Balance: Rs{new_bal}")
        except Exception:
            pass

    # ================================================================
    #  PAYMENT REJECT
    # ================================================================
    elif data.startswith("PAY_REJ|"):
        if tid != SUPER_ADMIN_ID:
            await q.answer("Sirf Admin reject kar sakta hai.", show_alert=True)
            return
        parts = data.split("|")
        if len(parts) < 5:
            return
        pay_id, c_tid_s, c_code, ag_id = parts[1], parts[2], parts[3], parts[4]
        agent = agent_by_id(ag_id)
        if agent:
            reject_payment(agent, pay_id)

        await q.edit_message_text(f"Payment REJECTED.\nID: {pay_id}")

        # Client notification — ALWAYS send keyboard after
        try:
            await ctx.bot.send_message(
                int(c_tid_s),
                f"Payment Reject Ho Gaya.\n\n"
                f"ID: {pay_id}\n"
                f"Koi galti hui ho to agent se contact karo.")
            # KEYBOARD HAMESHA BHEJNA HAI
            await ctx.bot.send_message(int(c_tid_s), "Apna panel:", reply_markup=kb_client())
        except Exception:
            pass

    # ================================================================
    #  QR / PAY — Low balance inline button → full payment flow
    # ================================================================
    elif data == "PAY_FLOW" or data == "GET_QR":
        c, ag = find_client(tid)
        if not c or not ag:
            return
        # Remove inline button from prev message
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        from handlers.client import _qr_and_ask
        await _qr_and_ask(tid, c, ag, ctx)
        # Amount will be caught by message_router via awaiting_pay_amount

    # ================================================================
    #  SETTINGS — Update Rate
    # ================================================================
    elif data == "ST_RATE":
        agent = agent_by_tid(tid)
        if not agent:
            return
        user_data[tid] = {"agent": agent, "awaiting_rate": True}
        await q.message.reply_text(
            f"Current Rate: Rs{safe_float(agent.get('rate_per_app', 0))}/app\n\n"
            f"Naya rate bhejiye (sirf number):",
            reply_markup=REMOVE)

    # ================================================================
    #  SETTINGS — Upload QR
    # ================================================================
    elif data == "ST_QR":
        agent = agent_by_tid(tid)
        if not agent:
            return
        user_data[tid] = {"agent": agent, "awaiting_qr": True}
        await q.message.reply_text(
            "Apna Payment QR Code photo bhejiye:",
            reply_markup=REMOVE)

    # ================================================================
    #  SETTINGS — Referral Link
    # ================================================================
    elif data == "ST_LINK":
        agent = agent_by_tid(tid)
        if not agent:
            return
        bot_me   = await ctx.bot.get_me()
        ref_link = f"https://t.me/{bot_me.username}?start=register_{agent['agent_id']}"
        await q.message.reply_text(
            f"Aapka Referral Link:\n\n{ref_link}\n\nYeh link clients ko bhejiye!")

    # ================================================================
    #  CLIENT — Block / Unblock
    # ================================================================
    elif data.startswith("C_BLOCK|"):
        parts  = data.split("|")
        if len(parts) < 3:
            return
        c_code, ag_id = parts[1], parts[2]
        agent = agent_by_id(ag_id)
        if not agent:
            return
        if str(tid) != str(agent.get("telegram_id", "")) and tid != SUPER_ADMIN_ID:
            await q.answer("Permission nahi.", show_alert=True)
            return
        set_client_field(agent, c_code, "status", "blocked")
        c = client_by_code(agent, c_code)
        if c:
            try:
                await ctx.bot.send_message(
                    safe_int(c["telegram_id"]),
                    "Aapka account block ho gaya. Agent se contact karein.")
            except Exception:
                pass
        await q.edit_message_text(f"{c_code} block ho gaya.")

    elif data.startswith("C_UNBLK|"):
        parts  = data.split("|")
        if len(parts) < 3:
            return
        c_code, ag_id = parts[1], parts[2]
        agent = agent_by_id(ag_id)
        if not agent:
            return
        set_client_field(agent, c_code, "status", "active")
        await q.edit_message_text(f"{c_code} unblock ho gaya.")

    # ================================================================
    #  AGENT — Block / Activate / Delete
    # ================================================================
    elif data.startswith("AG_BLOCK|"):
        if tid != SUPER_ADMIN_ID:
            await q.answer("Sirf Admin.", show_alert=True)
            return
        ag_id = data.split("|")[1]
        set_agent_field(ag_id, "status", "blocked")
        agent = agent_by_id(ag_id)
        master_log("AGENT_BLOCKED", agent["agent_name"] if agent else ag_id, ag_id)
        await q.edit_message_text(f"Agent {ag_id} block ho gaya.")
        if agent:
            try:
                await ctx.bot.send_message(
                    safe_int(agent["telegram_id"]),
                    "Aapka agent account block ho gaya. Admin se contact karein.")
            except Exception:
                pass

    elif data.startswith("AG_ACTIV|"):
        if tid != SUPER_ADMIN_ID:
            await q.answer("Sirf Admin.", show_alert=True)
            return
        ag_id = data.split("|")[1]
        te    = trial_end_date(TRIAL_DAYS)
        set_agent_field(ag_id, "status", "active")
        set_agent_field(ag_id, "trial_end", te)
        agent = agent_by_id(ag_id)
        await q.edit_message_text(f"Agent {ag_id} activated! Trial: {te}")
        if agent:
            try:
                await ctx.bot.send_message(
                    safe_int(agent["telegram_id"]),
                    f"Aapka account activate ho gaya!\nTrial: {te} tak\n/start karein.")
            except Exception:
                pass

    elif data.startswith("AG_DEL|"):
        if tid != SUPER_ADMIN_ID:
            await q.answer("Sirf Admin.", show_alert=True)
            return
        ag_id = data.split("|")[1]
        agent = agent_by_id(ag_id)
        remove_agent(ag_id)
        master_log("AGENT_DELETED", agent["agent_name"] if agent else ag_id, ag_id)
        await q.edit_message_text(f"Agent {ag_id} delete ho gaya.")
        if agent:
            try:
                await ctx.bot.send_message(
                    safe_int(agent["telegram_id"]),
                    "Aapka agent account delete ho gaya.")
            except Exception:
                pass

    # ================================================================
    #  BROADCAST TYPE (from agent broadcast conv)
    # ================================================================
    elif data.startswith("BC_"):
        from handlers.agent import bc_type_cb
        await bc_type_cb(update, ctx)
