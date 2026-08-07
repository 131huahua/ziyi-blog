"""演示 /admin/new 全流程：登录 → 传封面发文章 → 验证落地 → 清理"""
import requests

BASE = "http://127.0.0.1:8000"
s = requests.Session()

# 1. 登录
r = s.post(f"{BASE}/admin/login",
           data={"username": "admin", "password": "admin123"},
           allow_redirects=False)
print(f"1. 登录: {r.status_code} (303=成功重定向)")

# 2. 带封面上传发文章
with open("static/covers/cover3.png", "rb") as f:
    r2 = s.post(f"{BASE}/admin/new",
                data={"title": "演示：admin/new 全流程", "tags": "测试, 演示",
                      "content": "## 标题\n正文内容"},
                files={"cover": ("cover3.png", f, "image/png")},
                allow_redirects=False)
print(f"2. 发文章(带封面): {r2.status_code} (303=成功)")

# 3. 数据库验证
from sqlmodel import Session, select
from database import engine
from models import Post
db = Session(engine)
p = db.exec(select(Post).order_by(Post.id.desc())).first()
print(f"3. 数据库最新记录: id={p.id} | {p.title} | tags={p.tags}")
print(f"   cover_image = {p.cover_image}")

# 4. 前端能访问到新文章吗
r3 = s.get(f"{BASE}/post/{p.id}")
print(f"4. 新文章页面: {r3.status_code}, 标题在页内: {'演示' in r3.text}")
r4 = s.get(BASE + p.cover_image)
print(f"5. 封面图可访问: {r4.status_code}")

# 5. 清理演示数据
import pathlib
pathlib.Path("static", p.cover_image.removeprefix("/static/")).unlink(missing_ok=True)
db.delete(p)
db.commit()
print(f"6. 已清理演示文章(id={p.id})和封面文件")
