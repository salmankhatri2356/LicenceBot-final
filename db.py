# ================================================================
# db.py — Google Sheets Database
# SINGLE SHEET ARCHITECTURE: Sab kuch FOS_Master mein
#
# FOS_Master tabs:
#   agents        — sab agents ki list
#   logs          — master logs
#   clients_AGID  — har agent ke clients (e.g. clients_AGT1001)
#   apps_AGID     — har agent ki applications
#   payments_AGID — har agent ke payments
#   settings_AGID — agent settings (rate, qr etc)
# ================================================================

import re, logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound

from config import GOOGLE_CREDS, SCOPES, MASTER_SHEET, TRIAL_DAYS
from utils import now_ist, safe_float, safe_int, IST

logger = logging.getLogger(__name__)

# ── Tab Headers ───────────────────────────────────────────────
HDR = {
    "agents":  ["agent_id","agent_name","phone","telegram_id","sheet_name",
                "rate_per_app","qr_file_id","joined_at","status",
                "total_apps","total_clients","trial_end"],
    "logs":    ["event","agent","detail","timestamp"],
    "clients": ["client_code","full_name","phone","telegram_id",
                "joined_at","status","total_apps","balance"],
    "applications": ["app_id","app_no","dob","password","client_code",
                     "agent_id","created_at","status","done_at","balance_deducted"],
    "payments": ["payment_id","client_code","amount_paid","balance_added",
                 "payment_date","payment_time","status","approved_by","approved_at"],
    "settings": ["key","value"],
}


# ================================================================
# DB Class
# ================================================================

class DB:
    def __init__(self):
        self._gc = None
        self._sh = None   # cached FOS_Master sheet object

    def connect(self) -> bool:
        try:
            creds    = Credentials.from_service_account_info(GOOGLE_CREDS, scopes=SCOPES)
            self._gc = gspread.authorize(creds)
            self._sh = None
            logger.info("Google Sheets connected")
            return True
        except Exception as e:
            logger.error(f"connect error: {e}")
            return False

    def _client(self):
        if not self._gc:
            self.connect()
        return self._gc

    def master(self):
        """Return FOS_Master spreadsheet object (cached)."""
        if self._sh:
            try:
                # quick ping
                _ = self._sh.title
                return self._sh
            except Exception:
                self._sh = None
        try:
            self._sh = self._client().open(MASTER_SHEET)
            return self._sh
        except Exception:
            try:
                self.connect()
                self._sh = self._client().open(MASTER_SHEET)
                return self._sh
            except Exception as e:
                logger.error(f"master sheet open error: {e}")
                return None

    # kept for compat
    def open(self, name: str):
        if name == MASTER_SHEET:
            return self.master()
        return None

    def ws(self, sh, name: str):
        if sh is None:
            return None
        try:
            return sh.worksheet(name)
        except WorksheetNotFound:
            return None
        except Exception:
            return None

    def ensure_ws(self, tab: str, rows=1000, cols=20):
        """Get or create a tab in FOS_Master."""
        sh = self.master()
        if sh is None:
            return None
        try:
            return sh.worksheet(tab)
        except WorksheetNotFound:
            pass
        try:
            w = sh.add_worksheet(title=tab, rows=rows, cols=cols)
            if tab in HDR:
                w.append_row(HDR[tab])
            return w
        except Exception as e:
            logger.error(f"ensure_ws({tab}): {e}")
            return None

    def find_row(self, ws, key_col: int, key_val: str):
        """Returns (row_index_1based, row_dict) or (None, None)"""
        try:
            rows = ws.get_all_values()
            if not rows:
                return None, None
            headers = rows[0]
            for i, row in enumerate(rows[1:], start=2):
                while len(row) < len(headers):
                    row.append("")
                if row[key_col] == key_val:
                    return i, dict(zip(headers, row))
        except Exception:
            pass
        return None, None

    def update_field(self, ws, key_col: int, key_val: str, field: str, value) -> bool:
        try:
            rows = ws.get_all_values()
            if not rows:
                return False
            headers = rows[0]
            if field not in headers:
                return False
            col = headers.index(field) + 1
            for i, row in enumerate(rows[1:], start=2):
                if len(row) > key_col and row[key_col] == key_val:
                    ws.update_cell(i, col, value)
                    return True
        except Exception as e:
            logger.error(f"update_field: {e}")
        return False

    def rows_to_dicts(self, ws) -> list:
        try:
            rows = ws.get_all_values()
            if len(rows) < 2:
                return []
            headers = rows[0]
            result  = []
            for row in rows[1:]:
                while len(row) < len(headers):
                    row.append("")
                result.append(dict(zip(headers, row)))
            return result
        except Exception:
            return []


db = DB()


# ================================================================
# Tab name helpers
# ================================================================

def _tab(agent_id: str, kind: str) -> str:
    """e.g. clients_AGT1001"""
    aid = agent_id.replace("-", "").replace(" ", "")
    return f"{kind}_{aid}"


def _agent_ws(agent: dict, kind: str):
    """Get or create agent-specific tab in FOS_Master."""
    aid = agent.get("agent_id", "")
    if not aid:
        return None
    tab = _tab(aid, kind)
    return db.ensure_ws(tab)


# ================================================================
# Master sheet helpers
# ================================================================

def _aws():
    """agents worksheet"""
    return db.ensure_ws("agents")

def _mlws():
    """logs worksheet"""
    return db.ensure_ws("logs")


# ================================================================
# AGENTS
# ================================================================

def all_agents() -> list:
    w = _aws()
    if w is None:
        return []
    return db.rows_to_dicts(w)


def agent_by_tid(tid: int):
    for a in all_agents():
        if str(a.get("telegram_id", "")) == str(tid):
            return a
    return None


def agent_by_id(aid: str):
    for a in all_agents():
        if a.get("agent_id", "") == aid:
            return a
    return None


def add_agent(data: dict) -> bool:
    try:
        w = _aws()
        if w is None:
            return False
        trial_end = (datetime.now(IST) + timedelta(days=TRIAL_DAYS)).strftime("%Y-%m-%d")
        # sheet_name = agent_id (same sheet, just tabs)
        aid = data["agent_id"]
        row = [
            aid, data["agent_name"], data["phone"],
            data["telegram_id"], aid,          # sheet_name = agent_id
            data["rate"], "", now_ist(), "trial", 0, 0, trial_end,
        ]
        w.append_row(row)
        master_log("AGENT_ADDED", data["agent_name"], f"ID:{aid} trial:{trial_end}")
        return True
    except Exception as e:
        logger.error(f"add_agent: {e}")
        return False


def set_agent_field(agent_id: str, field: str, value) -> bool:
    w = _aws()
    if w is None:
        return False
    return db.update_field(w, 0, agent_id, field, value)


def remove_agent(agent_id: str) -> bool:
    try:
        w = _aws()
        if w is None:
            return False
        ri, _ = db.find_row(w, 0, agent_id)
        if ri:
            w.delete_rows(ri)
            return True
    except Exception as e:
        logger.error(f"remove_agent: {e}")
    return False


def agent_status(agent: dict) -> str:
    st = str(agent.get("status", "active"))
    if st in ("blocked", "deleted", "expired"):
        return st
    if st == "trial":
        te = str(agent.get("trial_end", ""))
        if te:
            try:
                ed = datetime.strptime(te, "%Y-%m-%d").replace(tzinfo=IST)
                if datetime.now(IST) > ed:
                    return "expired"
            except Exception:
                pass
    return st


def trial_end_date(days=TRIAL_DAYS) -> str:
    return (datetime.now(IST) + timedelta(days=days)).strftime("%Y-%m-%d")


def master_log(event: str, agent: str, detail: str):
    try:
        w = _mlws()
        if w:
            w.append_row([event, agent, detail, now_ist()])
    except Exception:
        pass


def agent_log(agent: dict, event: str, user: str, role: str, detail: str = ""):
    """Log to agent-specific log (stored in master sheet as logs tab)."""
    master_log(event, user, detail)


# ================================================================
# AGENT SETUP — no new sheet, just tabs in FOS_Master
# ================================================================

def make_agent_sheet(agent_name: str, tid: str) -> str:
    """
    Old API kept. Now just returns agent_id placeholder.
    Actual tabs created on first use via _agent_ws().
    Returns a dummy sheet_name = agent_id (set later).
    """
    return "PENDING"   # will be replaced with agent_id after add_agent


def setup_agent_tabs(agent_id: str, agent_name: str, rate: float):
    """Create all tabs for a new agent in FOS_Master."""
    agent = {"agent_id": agent_id}
    for kind in ("clients", "applications", "payments", "settings"):
        w = _agent_ws(agent, kind)
        if w is None:
            logger.error(f"Could not create tab {kind} for {agent_id}")
            continue
    # Seed settings
    try:
        sw = _agent_ws(agent, "settings")
        rows = db.rows_to_dicts(sw)
        keys = {r["key"] for r in rows}
        if "rate_per_app" not in keys:
            sw.append_row(["rate_per_app", str(rate)])
        if "qr_file_id" not in keys:
            sw.append_row(["qr_file_id", ""])
        if "agent_name" not in keys:
            sw.append_row(["agent_name", agent_name])
    except Exception as e:
        logger.error(f"setup_agent_tabs settings: {e}")


# ================================================================
# SETTINGS
# ================================================================

def get_setting(agent: dict, key: str) -> str:
    try:
        w = _agent_ws(agent, "settings")
        if w is None:
            return ""
        for row in db.rows_to_dicts(w):
            if row.get("key") == key:
                return row.get("value", "")
    except Exception:
        pass
    return ""


def put_setting(agent: dict, key: str, value: str) -> bool:
    try:
        w = _agent_ws(agent, "settings")
        if w is None:
            return False
        rows = w.get_all_values()
        headers = rows[0] if rows else ["key", "value"]
        for i, row in enumerate(rows[1:], start=2):
            if row and row[0] == key:
                w.update_cell(i, 2, value)
                return True
        w.append_row([key, value])
        return True
    except Exception as e:
        logger.error(f"put_setting: {e}")
        return False


# ================================================================
# CLIENTS
# ================================================================

def all_clients(agent: dict) -> list:
    w = _agent_ws(agent, "clients")
    if w is None:
        return []
    return db.rows_to_dicts(w)


def find_client(tid: int):
    """Search all agents for this client TID. Returns (client, agent) or ({}, {})"""
    for ag in all_agents():
        st = agent_status(ag)
        if st in ("deleted",):
            continue
        for c in all_clients(ag):
            if str(c.get("telegram_id", "")) == str(tid):
                return c, ag
    return {}, {}


def client_by_code(agent: dict, code: str):
    for c in all_clients(agent):
        if c.get("client_code") == code:
            return c
    return None


def add_client(agent: dict, data: dict) -> bool:
    try:
        w = _agent_ws(agent, "clients")
        if w is None:
            return False
        row = [
            data["client_code"], data["full_name"], data["phone"],
            data["telegram_id"], now_ist(), "active", 0, 0,
        ]
        w.append_row(row)
        # Update agent total_clients
        try:
            cur = safe_int(agent.get("total_clients", 0))
            set_agent_field(agent["agent_id"], "total_clients", cur + 1)
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error(f"add_client: {e}")
        return False


def set_client_field(agent: dict, client_code: str, field: str, value) -> bool:
    w = _agent_ws(agent, "clients")
    if w is None:
        return False
    return db.update_field(w, 0, client_code, field, value)


def get_balance(agent: dict, client_code: str) -> float:
    w = _agent_ws(agent, "clients")
    if w is None:
        return 0.0
    _, row = db.find_row(w, 0, client_code)
    return safe_float(row.get("balance", 0)) if row else 0.0


def add_balance(agent: dict, client_code: str, amount: float) -> bool:
    cur = get_balance(agent, client_code)
    return set_client_field(agent, client_code, "balance", round(cur + amount, 2))


def deduct_balance(agent: dict, client_code: str, amount: float) -> bool:
    cur = get_balance(agent, client_code)
    if cur < amount:
        return False
    return set_client_field(agent, client_code, "balance", round(cur - amount, 2))


def inc_client_apps(agent: dict, client_code: str):
    w = _agent_ws(agent, "clients")
    if w is None:
        return
    _, row = db.find_row(w, 0, client_code)
    if row:
        cur = safe_int(row.get("total_apps", 0))
        db.update_field(w, 0, client_code, "total_apps", cur + 1)


# ================================================================
# APPLICATIONS
# ================================================================

def all_apps(agent: dict) -> list:
    w = _agent_ws(agent, "applications")
    if w is None:
        return []
    return db.rows_to_dicts(w)


def app_by_id(agent: dict, app_id: str):
    for a in all_apps(agent):
        if a.get("app_id") == app_id:
            return a
    return None


def app_exists(agent: dict, app_no: str, client_code: str) -> bool:
    for a in all_apps(agent):
        if a.get("app_no") == app_no and a.get("client_code") == client_code:
            return True
    return False


def add_app(agent: dict, data: dict) -> bool:
    try:
        w = _agent_ws(agent, "applications")
        if w is None:
            return False
        row = [
            data["app_id"], data["app_no"], data["dob"], data["password"],
            data["client_code"], agent.get("agent_id", ""),
            now_ist(), "PENDING", "", "",
        ]
        w.append_row(row)
        try:
            cur = safe_int(agent.get("total_apps", 0))
            set_agent_field(agent["agent_id"], "total_apps", cur + 1)
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error(f"add_app: {e}")
        return False


def mark_done(agent: dict, app_id: str) -> bool:
    w = _agent_ws(agent, "applications")
    if w is None:
        return False
    ok1 = db.update_field(w, 0, app_id, "status",  "DONE")
    ok2 = db.update_field(w, 0, app_id, "done_at", now_ist())
    return ok1


# ================================================================
# PAYMENTS
# ================================================================

def all_payments(agent: dict) -> list:
    w = _agent_ws(agent, "payments")
    if w is None:
        return []
    return db.rows_to_dicts(w)


def add_payment(agent: dict, data: dict) -> bool:
    try:
        w = _agent_ws(agent, "payments")
        if w is None:
            return False
        now = datetime.now(IST)
        row = [
            data["pay_id"], data["client_code"], data["amount"], "",
            now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"),
            "PENDING", "", "",
        ]
        w.append_row(row)
        return True
    except Exception as e:
        logger.error(f"add_payment: {e}")
        return False


def approve_payment(agent: dict, pay_id: str, approved_by: str) -> bool:
    w = _agent_ws(agent, "payments")
    if w is None:
        return False
    db.update_field(w, 0, pay_id, "status",      "PAID")
    db.update_field(w, 0, pay_id, "approved_by", approved_by)
    db.update_field(w, 0, pay_id, "approved_at", now_ist())
    return True


def reject_payment(agent: dict, pay_id: str) -> bool:
    w = _agent_ws(agent, "payments")
    if w is None:
        return False
    db.update_field(w, 0, pay_id, "status", "REJECTED")
    return True


# ================================================================
# detect_role
# ================================================================

def detect_role(tid: int) -> str:
    from config import SUPER_ADMIN_ID
    if tid == SUPER_ADMIN_ID:
        return "admin"
    if agent_by_tid(tid):
        return "agent"
    c, _ = find_client(tid)
    if c:
        return "client"
    return "unknown"
