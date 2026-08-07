"""数据库配置：开发用 SQLite，上线换成 PostgreSQL。

上线时设置环境变量即可：
  BLOG_DB_URL=postgresql://user:pass@localhost:5432/blog
"""
import os

from sqlmodel import SQLModel, create_engine

DB_URL = os.getenv("BLOG_DB_URL", "sqlite:///blog.db")

# SQLite 需要 check_same_thread=False（FastAPI 多线程访问）
connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, connect_args=connect_args)


def init_db():
    """建表（没有就创建）"""
    SQLModel.metadata.create_all(engine)
