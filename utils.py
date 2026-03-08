# ================================================================
# utils.py — Common Helper Functions
# ================================================================

import re, random, string, logging
from datetime import datetime
from zoneinfo import ZoneInfo

IST    = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger(__name__)

# Global temp storage for multi-step conversations
user_data: dict = {}


def now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

def today_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")

def month_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m")

def safe_float(v) -> float:
    try:    return float(v)
    except: return 0.0

def safe_int(v) -> int:
    try:    return int(float(v))
    except: return 0

def gen_client_code() -> str:
    return f"FOS-{random.randint(1000,9999)}-{random.randint(100,999)}"

def gen_agent_id() -> str:
    return f"AGT-{random.randint(1000,9999)}"

def gen_app_id() -> str:
    return f"APP-{''.join(random.choices(string.digits, k=5))}"

def gen_pay_id() -> str:
    return f"PAY-{''.join(random.choices(string.digits, k=5))}"

def valid_phone(p: str) -> bool:
    return bool(re.fullmatch(r'\d{10}', p.strip()))

def valid_dob(d: str) -> bool:
    return bool(re.fullmatch(r'\d{2}/\d{2}/\d{4}', d.strip()))

def divider() -> str:
    return "━━━━━━━━━━━━━━━━━━━━━━━"
