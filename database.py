# ============================================================
#   DEKU VPS MANAGER — Database Layer
# ============================================================

import sqlite3
import random
import string
from datetime import datetime, timedelta
from config import DB_PATH, ADMIN_ID, ADMIN_USERNAME


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS admins (
            telegram_id   INTEGER PRIMARY KEY,
            username      TEXT,
            added_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS users (
            telegram_id   INTEGER PRIMARY KEY,
            username      TEXT,
            first_name    TEXT,
            code_used     TEXT,
            quota_max     INTEGER DEFAULT 0,
            accounts_used INTEGER DEFAULT 0,
            is_blocked    INTEGER DEFAULT 0,
            joined_at     TEXT DEFAULT (datetime('now')),
            last_action   TEXT
        );

        CREATE TABLE IF NOT EXISTS access_codes (
            code          TEXT PRIMARY KEY,
            validity_days INTEGER,
            quota_max     INTEGER,
            max_uses      INTEGER,
            uses_left     INTEGER,
            created_by    INTEGER,
            created_at    TEXT DEFAULT (datetime('now')),
            expires_at    TEXT,
            is_active     INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id      INTEGER,
            ssh_user      TEXT UNIQUE,
            ssh_pass      TEXT,
            vps_ip        TEXT,
            port          INTEGER,
            account_type  TEXT,
            max_sessions  INTEGER DEFAULT 0,
            created_at    TEXT DEFAULT (datetime('now')),
            expires_at    TEXT,
            is_active     INTEGER DEFAULT 1,
            FOREIGN KEY(owner_id) REFERENCES users(telegram_id)
        );

        CREATE TABLE IF NOT EXISTS v2ray_accounts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id      INTEGER,
            username      TEXT,
            uuid          TEXT UNIQUE,
            protocol      TEXT,
            sni_host      TEXT DEFAULT '',
            sni_mode      TEXT DEFAULT 'none',
            max_sessions  INTEGER DEFAULT 0,
            vps_ip        TEXT,
            path          TEXT DEFAULT '/deku',
            created_at    TEXT DEFAULT (datetime('now')),
            expires_at    TEXT,
            is_active     INTEGER DEFAULT 1,
            FOREIGN KEY(owner_id) REFERENCES users(telegram_id)
        );

        CREATE TABLE IF NOT EXISTS login_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id    INTEGER,
            account_type  TEXT,
            ssh_user      TEXT,
            src_ip        TEXT,
            login_at      TEXT,
            recorded_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS logs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id   INTEGER,
            username      TEXT,
            action        TEXT,
            detail        TEXT,
            timestamp     TEXT DEFAULT (datetime('now'))
        );
    """)

    # Migrations colonnes manquantes (DB existante)
    for migration in [
        "ALTER TABLE accounts ADD COLUMN max_sessions INTEGER DEFAULT 0",
    ]:
        try:
            c.execute(migration)
        except Exception:
            pass

    c.execute(
        "INSERT OR IGNORE INTO admins (telegram_id, username) VALUES (?, ?)",
        (ADMIN_ID, ADMIN_USERNAME)
    )
    conn.commit()
    conn.close()


# ── Admins ───────────────────────────────────────────────────

def is_admin(telegram_id: int) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM admins WHERE telegram_id = ?", (telegram_id,)
    ).fetchone()
    conn.close()
    return row is not None


def add_admin(telegram_id: int, username: str):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO admins (telegram_id, username) VALUES (?, ?)",
        (telegram_id, username)
    )
    conn.commit()
    conn.close()


def get_all_admins():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM admins").fetchall()
    conn.close()
    return rows


# ── Users ────────────────────────────────────────────────────

def get_user(telegram_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    ).fetchone()
    conn.close()
    return row


def register_user(telegram_id: int, username: str, first_name: str,
                  code: str, quota_max: int):
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO users
            (telegram_id, username, first_name, code_used, quota_max, accounts_used)
        VALUES (?, ?, ?, ?, ?, 0)
    """, (telegram_id, username, first_name, code, quota_max))
    conn.commit()
    conn.close()


def update_user_last_action(telegram_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET last_action = datetime('now') WHERE telegram_id = ?",
        (telegram_id,)
    )
    conn.commit()
    conn.close()


def block_user(telegram_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET is_blocked = 1 WHERE telegram_id = ?", (telegram_id,)
    )
    conn.commit()
    conn.close()


def unblock_user(telegram_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET is_blocked = 0 WHERE telegram_id = ?", (telegram_id,)
    )
    conn.commit()
    conn.close()


def delete_user(telegram_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()


def get_all_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY joined_at DESC").fetchall()
    conn.close()
    return rows


def is_registered(telegram_id: int) -> bool:
    return get_user(telegram_id) is not None


def is_blocked(telegram_id: int) -> bool:
    user = get_user(telegram_id)
    return user and user["is_blocked"] == 1


# ── Codes d'accès ────────────────────────────────────────────

def _rand_code(length=12) -> str:
    chars = string.ascii_uppercase + string.digits
    return "DEKU-" + "".join(random.choices(chars, k=length))


def create_code(validity_days: int, quota_max: int,
                max_uses: int, created_by: int) -> str:
    code = _rand_code()
    expires_at = (datetime.now() + timedelta(days=validity_days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn = get_conn()
    conn.execute("""
        INSERT INTO access_codes
            (code, validity_days, quota_max, max_uses, uses_left, created_by, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (code, validity_days, quota_max, max_uses, max_uses, created_by, expires_at))
    conn.commit()
    conn.close()
    return code


def validate_code(code: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM access_codes WHERE code = ? AND is_active = 1", (code,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    if row["uses_left"] <= 0:
        return None
    if datetime.now() > datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S"):
        return None
    return row


def consume_code(code: str):
    conn = get_conn()
    conn.execute(
        "UPDATE access_codes SET uses_left = uses_left - 1 WHERE code = ?", (code,)
    )
    conn.commit()
    conn.close()


def get_all_codes():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM access_codes ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return rows


def deactivate_code(code: str):
    conn = get_conn()
    conn.execute(
        "UPDATE access_codes SET is_active = 0 WHERE code = ?", (code,)
    )
    conn.commit()
    conn.close()


# ── Comptes SSH ──────────────────────────────────────────────

def _gen_password(length=12) -> str:
    chars = string.ascii_letters + string.digits + "!@#$"
    return "".join(random.choices(chars, k=length))


def create_account(owner_id: int, ssh_user: str, vps_ip: str,
                   port: int, account_type: str, validity_days: int,
                   max_sessions: int = 0) -> dict:
    ssh_pass = _gen_password()
    expires_at = (datetime.now() + timedelta(days=validity_days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn = get_conn()
    conn.execute("""
        INSERT INTO accounts
            (owner_id, ssh_user, ssh_pass, vps_ip, port,
             account_type, max_sessions, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (owner_id, ssh_user, ssh_pass, vps_ip, port,
          account_type, max_sessions, expires_at))
    conn.execute(
        "UPDATE users SET accounts_used = accounts_used + 1 WHERE telegram_id = ?",
        (owner_id,)
    )
    conn.commit()
    conn.close()
    return {
        "ssh_user": ssh_user, "ssh_pass": ssh_pass,
        "vps_ip": vps_ip, "port": port,
        "account_type": account_type, "expires_at": expires_at,
        "max_sessions": max_sessions,
    }


def get_user_accounts(owner_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM accounts WHERE owner_id = ? ORDER BY created_at DESC",
        (owner_id,)
    ).fetchall()
    conn.close()
    return rows


def get_all_accounts():
    conn = get_conn()
    rows = conn.execute(
        "SELECT a.*, u.username FROM accounts a "
        "LEFT JOIN users u ON a.owner_id = u.telegram_id "
        "ORDER BY a.created_at DESC"
    ).fetchall()
    conn.close()
    return rows


def get_account_by_id(account_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    conn.close()
    return row


def delete_account(account_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT owner_id FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE users SET accounts_used = MAX(0, accounts_used - 1) WHERE telegram_id = ?",
            (row["owner_id"],)
        )
    conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    conn.commit()
    conn.close()


def renew_account(account_id: int, days: int):
    conn = get_conn()
    conn.execute("""
        UPDATE accounts
        SET expires_at = datetime(expires_at, ? || ' days'), is_active = 1
        WHERE id = ?
    """, (f"+{days}", account_id))
    conn.commit()
    conn.close()


def get_expired_accounts():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM accounts WHERE expires_at < datetime('now') AND is_active = 1"
    ).fetchall()
    conn.close()
    return rows


def deactivate_expired():
    conn = get_conn()
    conn.execute(
        "UPDATE accounts SET is_active = 0 "
        "WHERE expires_at < datetime('now') AND is_active = 1"
    )
    conn.commit()
    conn.close()


def get_user_quota(telegram_id: int) -> tuple:
    conn = get_conn()
    row = conn.execute(
        "SELECT quota_max, accounts_used FROM users WHERE telegram_id = ?",
        (telegram_id,)
    ).fetchone()
    conn.close()
    if not row:
        return (0, 0)
    return (row["quota_max"], row["accounts_used"])


def username_exists(ssh_user: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM accounts WHERE ssh_user = ?", (ssh_user,)
    ).fetchone()
    conn.close()
    return row is not None


# ── Comptes V2Ray ─────────────────────────────────────────────

def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())


def v2ray_username_exists(username: str, owner_id: int) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM v2ray_accounts WHERE username = ? AND owner_id = ?",
        (username, owner_id)
    ).fetchone()
    conn.close()
    return row is not None


def create_v2ray_account(owner_id: int, username: str, protocol: str,
                         sni_host: str, sni_mode: str, max_sessions: int,
                         vps_ip: str, validity_days: int,
                         path: str = "/deku") -> dict:
    uuid_val = _gen_uuid()
    expires_at = (datetime.now() + timedelta(days=validity_days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn = get_conn()
    conn.execute("""
        INSERT INTO v2ray_accounts
            (owner_id, username, uuid, protocol, sni_host, sni_mode,
             max_sessions, vps_ip, path, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (owner_id, username, uuid_val, protocol, sni_host, sni_mode,
          max_sessions, vps_ip, path, expires_at))
    conn.execute(
        "UPDATE users SET accounts_used = accounts_used + 1 WHERE telegram_id = ?",
        (owner_id,)
    )
    conn.commit()
    conn.close()
    return {
        "uuid": uuid_val, "username": username, "protocol": protocol,
        "sni_host": sni_host, "sni_mode": sni_mode,
        "max_sessions": max_sessions, "vps_ip": vps_ip,
        "path": path, "expires_at": expires_at,
    }


def get_v2ray_account_by_id(acc_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM v2ray_accounts WHERE id = ?", (acc_id,)
    ).fetchone()
    conn.close()
    return row


def get_user_v2ray_accounts(owner_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM v2ray_accounts WHERE owner_id = ? ORDER BY created_at DESC",
        (owner_id,)
    ).fetchall()
    conn.close()
    return rows


def get_all_v2ray_accounts():
    conn = get_conn()
    rows = conn.execute(
        "SELECT v.*, u.username AS tg_username FROM v2ray_accounts v "
        "LEFT JOIN users u ON v.owner_id = u.telegram_id "
        "ORDER BY v.created_at DESC"
    ).fetchall()
    conn.close()
    return rows


def delete_v2ray_account(acc_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT owner_id FROM v2ray_accounts WHERE id = ?", (acc_id,)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE users SET accounts_used = MAX(0, accounts_used - 1) WHERE telegram_id = ?",
            (row["owner_id"],)
        )
    conn.execute("DELETE FROM v2ray_accounts WHERE id = ?", (acc_id,))
    conn.commit()
    conn.close()


def renew_v2ray_account(acc_id: int, days: int):
    conn = get_conn()
    conn.execute("""
        UPDATE v2ray_accounts
        SET expires_at = datetime(expires_at, ? || ' days'), is_active = 1
        WHERE id = ?
    """, (f"+{days}", acc_id))
    conn.commit()
    conn.close()


def get_expired_v2ray_accounts():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM v2ray_accounts WHERE expires_at < datetime('now') AND is_active = 1"
    ).fetchall()
    conn.close()
    return rows


def deactivate_expired_v2ray():
    conn = get_conn()
    conn.execute(
        "UPDATE v2ray_accounts SET is_active = 0 "
        "WHERE expires_at < datetime('now') AND is_active = 1"
    )
    conn.commit()
    conn.close()


# ── Historique connexions ─────────────────────────────────────

def save_login_history(account_id: int, account_type: str,
                       ssh_user: str, src_ip: str, login_at: str):
    conn = get_conn()
    conn.execute("""
        INSERT INTO login_history (account_id, account_type, ssh_user, src_ip, login_at)
        VALUES (?, ?, ?, ?, ?)
    """, (account_id, account_type, ssh_user, src_ip, login_at))
    conn.commit()
    conn.close()


def get_login_history(ssh_user: str, limit: int = 10):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM login_history WHERE ssh_user = ? ORDER BY recorded_at DESC LIMIT ?",
        (ssh_user, limit)
    ).fetchall()
    conn.close()
    return rows


# ── Logs ─────────────────────────────────────────────────────

def add_log(telegram_id: int, username: str, action: str, detail: str = ""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO logs (telegram_id, username, action, detail) VALUES (?, ?, ?, ?)",
        (telegram_id, username, action, detail)
    )
    conn.commit()
    conn.close()


def get_logs(limit: int = 50):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


# ── Stats ─────────────────────────────────────────────────────

def get_stats() -> dict:
    conn = get_conn()
    total_users     = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_accounts  = conn.execute(
        "SELECT COUNT(*) FROM accounts WHERE is_active = 1"
    ).fetchone()[0]
    total_v2ray     = conn.execute(
        "SELECT COUNT(*) FROM v2ray_accounts WHERE is_active = 1"
    ).fetchone()[0]
    total_codes     = conn.execute(
        "SELECT COUNT(*) FROM access_codes WHERE is_active = 1"
    ).fetchone()[0]
    expired         = conn.execute(
        "SELECT COUNT(*) FROM accounts WHERE expires_at < datetime('now')"
    ).fetchone()[0]
    expired_v2      = conn.execute(
        "SELECT COUNT(*) FROM v2ray_accounts WHERE expires_at < datetime('now')"
    ).fetchone()[0]
    blocked         = conn.execute(
        "SELECT COUNT(*) FROM users WHERE is_blocked = 1"
    ).fetchone()[0]
    conn.close()
    return {
        "total_users": total_users,
        "total_accounts": total_accounts,
        "total_v2ray": total_v2ray,
        "total_codes": total_codes,
        "expired_accounts": expired + expired_v2,
        "blocked_users": blocked,
    }
