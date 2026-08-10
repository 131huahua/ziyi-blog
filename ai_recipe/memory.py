"""记忆功能：SQLite 存储用户画像（长期记忆）+ 对话历史（短期记忆）

- users 表：每个访客一行，存口味/忌口/人数/健康目标等画像 JSON
- messages 表：每轮对话都存，回答时把最近 N 条拼进上下文
- 纯标准库 sqlite3，无需额外依赖
"""
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from ai_recipe.config import settings

DB_PATH = Path(settings.memory_db_path)
_lock = threading.Lock()

# 画像字段白名单（防脏数据）
PROFILE_FIELDS = {
    "role": str,          # chef / nutritionist
    "口味偏好": list,
    "忌口": list,
    "人数": int,
    "健康目标": str,
    "常备食材": list,
}

DEFAULT_PROFILE = {
    "role": "chef",
    "口味偏好": [],
    "忌口": [],
    "人数": None,
    "健康目标": None,
    "常备食材": [],
}


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                profile TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                ts TEXT NOT NULL
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id, id)"
        )


# ---------------- 用户画像（长期记忆） ----------------

def get_profile(user_id: str) -> dict:
    """读取用户画像，没有则返回默认值（并自动建行）"""
    init_db()
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT profile FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    if row is None:
        profile = dict(DEFAULT_PROFILE)
        with _lock, _connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, profile, created_at) VALUES (?, ?, ?)",
                (user_id, json.dumps(profile, ensure_ascii=False), datetime.now().isoformat()),
            )
        return profile
    try:
        profile = json.loads(row["profile"])
    except json.JSONDecodeError:
        profile = {}
    return {**DEFAULT_PROFILE, **profile}


def update_profile(user_id: str, **fields) -> dict:
    """更新画像。只接受白名单字段；列表字段做合并去重。"""
    profile = get_profile(user_id)
    for key, value in fields.items():
        if key not in PROFILE_FIELDS:
            continue
        if value is None:
            continue
        expected = PROFILE_FIELDS[key]
        if expected is list:
            value = [str(v).strip() for v in value if str(v).strip()]
            if key in profile and isinstance(profile[key], list):
                value = list(dict.fromkeys(profile[key] + value))
        elif expected is int:
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
        else:
            value = str(value).strip()
            if not value:
                continue
        profile[key] = value

    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE users SET profile = ? WHERE user_id = ?",
            (json.dumps(profile, ensure_ascii=False), user_id),
        )
    return profile


# ---------------- 对话历史（短期记忆） ----------------

def add_message(user_id: str, role: str, content: str) -> None:
    init_db()
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, role, content, ts) VALUES (?, ?, ?, ?)",
            (user_id, role, content, datetime.now().isoformat()),
        )


def get_history(user_id: str, limit: int = 8) -> list[dict]:
    """取最近 limit 条对话（旧的在前）。"""
    init_db()
    with _lock, _connect() as conn:
        rows = conn.execute(
            """SELECT role, content FROM (
                   SELECT id, role, content FROM messages
                   WHERE user_id = ? ORDER BY id DESC LIMIT ?
               ) ORDER BY id ASC""",
            (user_id, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def clear_history(user_id: str) -> None:
    init_db()
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
