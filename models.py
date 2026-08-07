"""数据模型：文章"""
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Post(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    slug: str = Field(default="", index=True)
    content: str = ""            # Markdown 正文
    cover_image: str = ""        # 封面图路径，如 /static/covers/xxx.png
    tags: str = ""               # 逗号分隔，如 "随笔, 技术"
    created_at: datetime = Field(default_factory=now_utc)


class SiteConfig(SQLModel, table=True):
    """全站配置：键值对存储（首页文案/背景图/关于页/社交链接等）"""
    key: str = Field(primary_key=True)   # 配置键，如 hero_title
    value: str = ""                      # 配置值


class Comment(SQLModel, table=True):
    """文章评论（自建轻量评论）"""
    id: int | None = Field(default=None, primary_key=True)
    post_id: int = Field(index=True)     # 所属文章
    name: str = ""                       # 昵称
    content: str = ""                    # 评论内容
    created_at: datetime = Field(default_factory=now_utc)


class StoredFile(SQLModel, table=True):
    """私人网盘：上传文件记录"""
    id: int | None = Field(default=None, primary_key=True)
    filename: str = ""                   # 服务器上的唯一存储名 (uuid.ext)
    original_name: str = ""              # 原始文件名
    file_size: int = 0                    # 大小（字节）
    file_type: str = "FILE"              # 后缀大写，如 ZIP/PNG/PDF
    is_public: bool = Field(default=False)  # True=前台公开，False=个人私密
    created_at: datetime = Field(default_factory=now_utc)


def format_file_size(size_bytes: int) -> str:
    """人类可读文件大小：B / KB / MB / GB"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


# 默认配置（数据库缺项时自动补全）
DEFAULT_CONFIGS = {
    "site_name": "ZIYI.",
    "hero_title": "听松涛与晨雾的低语",
    "hero_subtitle": "在深邃的森林角落，记录代码逻辑、视觉设计以及生活中的沉静思考。",
    "hero_bg_image": "/static/assets/mist-forest.jpg",
    "about_avatar": "/static/assets/avatar.png",
    "about_title": "你好，我是 ZIYI",
    "about_bio": "一名专注全栈开发与 UI 审美的创作者。\n\n热衷于利用 Python 与现代 Web 技术搭建极简沉浸的数字产品，记录代码与生活。",
    "github_url": "https://github.com/131huahua",
    "bgm_url": "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3",
    "bgm_title": "晨雾松涛",
    "bgm_lyric": "",  # .lrc 歌词地址（如 /static/audio/xxx.lrc），留空则不显示歌词
}
