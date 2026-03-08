# ================================================================
# keyboards.py — All ReplyKeyboard definitions
# ================================================================

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove

REMOVE = ReplyKeyboardRemove()

def kb_admin():
    return ReplyKeyboardMarkup([
        ["📊 Dashboard",      "👥 All Agents"],
        ["➕ Add Agent",      "🔍 Find Agent"],
        ["📋 All Apps",       "💰 All Payments"],
        ["📢 Broadcast All",  "🗂️ Logs"],
        ["📈 Monthly Report"],
    ], resize_keyboard=True)

def kb_agent():
    return ReplyKeyboardMarkup([
        ["📥 Pending Apps"],
        ["📊 Today Summary",  "📜 Work History"],
        ["👥 My Clients",     "📈 My Stats"],
        ["📢 Broadcast",      "⚙️ Settings"],
        ["🔄 Refresh"],
    ], resize_keyboard=True)

def kb_client():
    return ReplyKeyboardMarkup([
        ["📋 New Application"],
        ["📊 Today Summary",  "📜 My History"],
        ["💳 Pay / Get QR",   "💰 My Balance"],
        ["ℹ️ My Profile",     "📞 Contact Agent"],
    ], resize_keyboard=True)
