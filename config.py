# ================================================================
# config.py — FOS Bot Settings
# ================================================================

import os, json

BOT_TOKEN      = os.environ.get("BOT_TOKEN", "YAHAN_APNA_BOT_TOKEN_DAALO")
SUPER_ADMIN_ID = int(os.environ.get("SUPER_ADMIN_ID", "6806779180"))
MASTER_SHEET   = os.environ.get("MASTER_SHEET", "FOS_Master")
ADMIN_GMAIL    = "salmankhatri299@gmail.com"
TRIAL_DAYS     = 3

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── Google Credentials ────────────────────────────────────────
# Railway mein GOOGLE_CREDS_JSON environment variable mein
# poora JSON string paste karo (ek line mein)
_creds_json = os.environ.get("GOOGLE_CREDS_JSON", "")
if _creds_json:
    try:
        GOOGLE_CREDS = json.loads(_creds_json)
    except Exception as e:
        print(f"GOOGLE_CREDS_JSON parse error: {e}")
        GOOGLE_CREDS = {}
else:
    # Fallback: seedha dict (local testing ke liye)
    GOOGLE_CREDS = {
        "type": "service_account",
        "project_id": "",
        "private_key_id": "",
        "private_key": "",
        "client_email": "",
        "client_id": "",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "",
    }

# ── Conversation States ──────────────────────────────────────
(REG_NAME, REG_PHONE)               = range(2)
(AA_NAME, AA_PHONE, AA_TID, AA_RATE) = range(10, 14)
(APP_NO, APP_DOB, APP_PASS)          = range(20, 23)
(PAY_AMOUNT, PAY_CONFIRM)            = range(30, 32)
(BC_TYPE, BC_MSG)                    = range(40, 42)
(ABC_TYPE, ABC_MSG)                  = range(50, 52)
UR_RATE = 60
