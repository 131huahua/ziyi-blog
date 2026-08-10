"""AI 接口配额：Token 鉴权 + 调用次数限制（SQLite 持久化，跨 worker 安全）

规则（.env 可覆盖）：
- 匿名（无 token）：每 IP 10 分钟 ≤3 次，每天 ≤20 次
- 带有效 token（Authorization: Bearer xxx）：每天 ≤500 次
"""
import os
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "ai_quota.db"

NO_TOKEN_PER_WIN = int(os.getenv("AI_LIMIT_PER_10MIN", "3"))
NO_TOKEN_PER_DAY = int(os.getenv("AI_LIMIT_PER_DAY", "20"))
TOKEN_PER_DAY = int(os.getenv("AI_TOKEN_LIMIT_PER_DAY", "500"))

WIN_SECONDS = 600  # 10 分钟
DAY_SECONDS = 86400


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
    """从请求头提取 Bearer token"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return ""


def check_quota(ip: str, token: str) -> tuple[bool, str, int]:
    """返回 (允许, 提示语, 剩余次数)"""
    now = time.time()
    conn = _conn()
    if token and token in valid_tokens():
        n = conn.execute(
            "SELECT COUNT(*) FROM ai_usage WHERE token=? AND ts>?", (token, now - DAY_SECONDS)
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
        return False, f"问得太频繁啦，10 分钟内最多 {NO_TOKEN_PER_WIN} 次，歇口气再来～", remain
    if n_day >= NO_TOKEN_PER_DAY:
        return False, f"今天问得够多啦（上限 {NO_TOKEN_PER_DAY} 次），明天再来～", 0
    return True, f"今日剩余 {remain} 次", remain


def record(ip: str, token: str, ok: bool):
    """记录一次调用（放行后调用，无论问答成败都计入）"""
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
    # 清理 30 天前的数据
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
            "anonymous_per_10min": NO_TOKEN_PER_WIN,
            "anonymous_per_day": NO_TOKEN_PER_DAY,
            "token_per_day": TOKEN_PER_DAY,
        },
    }
