"""初始化数据库并写入 3 篇演示文章（封面用本地壁纸）"""
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from database import engine, init_db
from models import Post

DEMO = [
    dict(
        title="你好，世界 —— 我的新博客", slug="hello-world",
        tags="随笔, 开站", cover_image="/static/covers/cover1.png", days_ago=0,
        content="""这是第一篇博客。

用 **FastAPI + Jinja2** 从零搭建，目前支持：

- 封面图（发文章时上传）
- Markdown 写作
- 滚动渐入、打字机、封面视差动画

> 代码全是自己写的，慢慢完善。
""",
    ),
    dict(
        title="给博客加动画的几种姿势", slug="css-animations",
        tags="前端, 动画", cover_image="/static/covers/cover2.png", days_ago=1,
        content="""动画不一定要学框架，CSS 就够了。

## 常用套路

1. **滚动渐入**：`IntersectionObserver` + `.reveal` 类，10 行 JS
2. **卡片悬停**：`transform: scale()` + `transition`
3. **打字机**：几行 JS 定时器
4. **视差**：监听 `scroll` 改 `translateY`

```css
.card:hover img { transform: scale(1.08); }
```
""",
    ),
    dict(
        title="选一张好封面", slug="choose-cover",
        tags="设计", cover_image="/static/covers/cover3.png", days_ago=2,
        content="""封面是博客的门面。

- 列表页靠封面撑起视觉
- 详情页封面可以做 Hero 视差
- 素材可以先用本地壁纸，之后换成自己拍的图

> 一张好封面，胜过十段开场白。
""",
    ),
]


def main():
    init_db()
    with Session(engine) as db:
        if db.exec(select(Post)).first():
            print("数据库已有文章，跳过演示数据")
            return
        now = datetime.now(timezone.utc)
        for item in DEMO:
            db.add(Post(
                title=item["title"], slug=item["slug"], tags=item["tags"],
                cover_image=item["cover_image"], content=item["content"],
                created_at=now - timedelta(days=item["days_ago"]),
            ))
        db.commit()
        print(f"已写入 {len(DEMO)} 篇演示文章")


if __name__ == "__main__":
    main()
