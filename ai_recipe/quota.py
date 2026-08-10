"""AI 接口配额：Token 鉴权 + 调用次数限制（SQLite 持久化，跨 worker 安全）

规则（.env 可覆盖）：
- 匿名（无 token）：每 IP 30 分钟 ≤3 次，每天 ≤10 次
- 带有效 token（Authorization: Bearer ***）：每天 ≤20 次
- 其他防护：question 长度限制、并发限制、来源校验（见 check_request）
"""
import os
import sqlite3
import threading
import time
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "ai_quota.db"

NO_TOKEN_PER_WIN = int(os.getenv("AI_LIMIT_PER_WIN", "3"))
NO_TOKEN_PER_DAY = int(os.getenv("AI_LIMIT_PER_DAY", "10"))
TOKEN_PER_DAY = int(os.getenv("AI_TOKEN_LIMIT_PER_DAY", "20"))

WIN_SECONDS = int(os.getenv("AI_LIMIT_WIN_SECONDS", "1800"))  # 30 分钟
DAY_SECONDS = 86400
MAX_QUESTION_LEN = int(os.getenv("AI_MAX_QUESTION_LEN", "200"))  # 问题最大长度
MAX_CONCURRENT = int(os.getenv("AI_MAX_CONCURRENT", "2"))  # 单 IP 并发上限

# 内存并发计数（跨 worker 不精确但够用，防单点刷）
_concurrent: dict[str, int] = {}
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB), timeout=10)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS ai_usage ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT, token TEXT, ts REAL, ok INTEGER)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_ip ON ai_usage(ip, ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_tk ON ai_usage(token, ts)")
    conn.commit()
    return conn


def valid_tokens() -> set[str]:
    raw = os.getenv("AI_API_TOKENS", "")
    return {t.strip() for t in raw.split(",") if t.strip()}


def resolve_token(request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return ""


def check_origin(request) -> tuple[bool, str]:
    """来源校验：匿名浏览器请求必须来自本站（防跨站盗刷）"""
    origin = request.headers.get("Origin", "")
    referer = request.headers.get("Referer", "")
    if origin:
        if "ziyizhang.cn" not in origin and "localhost" not in origin and "127.0.0.1" not in origin:
            return False, "来源不被允许"
    elif referer:
        if "ziyizhang.cn" not in referer and "localhost" not in referer and "127.0.0.1" not in referer:
            return False, "来源不被允许"
    return True, ""


def check_question_len(question: str) -> tuple[bool, str]:
    if len(question) > MAX_QUESTION_LEN:
        return False, f"问题太长啦（最多 {MAX_QUESTION_LEN} 字），精简一下再问～"
    return True, ""


def check_quota(ip: str, token: str) -> tuple[bool, str, int]:
    """返回 (允许, 提示语, 剩余次数)"""
    now = time.time()
    conn = _conn()
    if token and token in valid_tokens():
        n = conn.execute(
            "SELECT COUNT(*) FROM ai_usage WHERE token=*** AND ts>?", (token, now - DAY_SECONDS)
        ).fetchone()[0]
        remain = max(TOKEN_PER_DAY - n, 0)
        if n >= TOKEN_PER_DAY:
            return False, f"今日调用已达上限（{TOKEN_PER_DAY} 次）", 0
        return True, f"Token 有效，今日剩余 {remain} 次", remain

    n_win = conn.execute(
        "SELECT COUNT(*) FROM ai_usage WHERE ip=? AND ts>?", (ip, now - WIN_SECONDS)
    ).fetchone()[0]
    n_day = conn.execute(
        "SELECT COUNT(*) FROM ai_usage WHERE ip=? AND ts>?", (ip, now - DAY_SECONDS)
    ).fetchone()[0]
    remain = max(NO_TOKEN_PER_DAY - n_day, 0)

    if n_win >= NO_TOKEN_PER_WIN:
        return False, f"问得太频繁啦，30 分钟内最多 {NO_TOKEN_PER_WIN} 次，歇口气再来～", remain
    if n_day >= NO_TOKEN_PER_DAY:
        return False, f"今天问得够多啦（上限 {NO_TOKEN_PER_DAY} 次），明天再来～", 0
    return True, f"今日剩余 {remain} 次", remain


def acquire_concurrent(ip: str) -> bool:
    """获取并发名额（进行中的请求数限制）"""
    with _lock:
        cur = _concurrent.get(ip, 0)
        if cur >= MAX_CONCURRENT:
            return False
        _concurrent[ip] = cur + 1
        return True


def release_concurrent(ip: str):
    with _lock:
        cur = _concurrent.get(ip, 0)
        if cur <= 1:
            _concurrent.pop(ip, None)
        else:
            _concurrent[ip] = cur - 1


def record(ip: str, token: str, ok: bool):
    conn = _conn()
    conn.execute(
        "INSERT INTO ai_usage (ip, token, ts, ok) VALUES (?,?,?,?)",
        (ip, token, time.time(), 1 if ok else 0),
    )
    conn.commit()


def today_stats() -> dict:
    """今日统计（后台面板用）"""
    conn = _conn()
    day_start = time.time() - DAY_SECONDS
    total = conn.execute("SELECT COUNT(*) FROM ai_usage WHERE ts>?", (day_start,)).fetchone()[0]
    ok = conn.execute("SELECT COUNT(*) FROM ai_usage WHERE ts>? AND ok=1", (day_start,)).fetchone()[0]
    by_ip = conn.execute(
        "SELECT ip, COUNT(*) FROM ai_usage WHERE ts>? GROUP BY ip ORDER BY COUNT(*) DESC LIMIT 10",
        (day_start,),
    ).fetchall()
    by_token = conn.execute(
        "SELECT token, COUNT(*) FROM ai_usage WHERE ts>? AND token != '' GROUP BY token ORDER BY COUNT(*) DESC LIMIT 10",
        (day_start,),
    ).fetchall()
    conn.execute("DELETE FROM ai_usage WHERE ts<?", (time.time() - 30 * DAY_SECONDS,))
    conn.commit()
    return {
        "total": total,
        "ok": ok,
        "blocked": total - ok,
        "by_ip": [{"ip": ip, "count": c} for ip, c in by_ip],
        "by_token": [{"token": t, "count": c} for t, c in by_token],
        "tokens": sorted(valid_tokens()),
        "limits": {
            "window_seconds": WIN_SECONDS,
            "anonymous_per_window": NO_TOKEN_PER_WIN,
            "anonymous_per_day": NO_TOKEN_PER_DAY,
            "token_per_day": TOKEN_PER_DAY,
            "max_question_len": MAX_QUESTION_LEN,
            "max_concurrent": MAX_CONCURRENT,
        },
    }
