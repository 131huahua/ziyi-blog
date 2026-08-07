"""后台登录：最简单的 session 方式。

上线前务必通过环境变量改掉默认密码：
  BLOG_ADMIN_USER=xxx  BLOG_ADMIN_PASS=xxx
更安全：BLOG_ADMIN_PASS_HASH=<sha256>（不存明文）
"""
import hashlib
import os

from fastapi import Request

ADMIN_USER = os.getenv("BLOG_ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("BLOG_ADMIN_PASS", "admin123")
ADMIN_PASS_HASH = os.getenv("BLOG_ADMIN_PASS_HASH", "")


def is_logged_in(request: Request) -> bool:
    return request.session.get("admin") is True


def do_login(request: Request, username: str, password: str) -> bool:
    if username != ADMIN_USER:
        return False
    # 生产模式：比较 sha256 哈希（不存明文）；开发模式：明文比对
    if ADMIN_PASS_HASH:
        ok = hashlib.sha256(password.encode()).hexdigest() == ADMIN_PASS_HASH
    else:
        ok = password == ADMIN_PASS
    if ok:
        request.session["admin"] = True
        return True
    return False


def do_logout(request: Request):
    request.session.clear()
