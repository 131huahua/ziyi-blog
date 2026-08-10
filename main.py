"""FastAPI 博客骨架 —— 封面 + 动画

运行:  uvicorn main:app --reload   （默认 http://localhost:8000）
后台:  http://localhost:8000/admin   admin / admin123
"""
from collections import Counter
import io
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import markdown as md
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import StarletteHTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image
from sqlalchemy import or_
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

from auth import do_login, do_logout, is_logged_in
from database import engine, init_db
from models import DEFAULT_CONFIGS, Comment, Post, SiteConfig, StoredFile, format_file_size

BASE_DIR = Path(__file__).parent
COVERS_DIR = BASE_DIR / "static" / "covers"
COVERS_DIR.mkdir(parents=True, exist_ok=True)
# 私人网盘存储目录
PRIVATE_STORAGE_DIR = BASE_DIR / "storage" / "private"
PRIVATE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

SESSION_KEY = "blog-secret-change-me"  # 上线前换成随机字符串

# ---------- 全站配置缓存 ----------
CONFIG_CACHE: dict = {}


def load_config(db: Session) -> dict:
    """从数据库读取全部配置，缺项补默认值，并刷新缓存"""
    global CONFIG_CACHE
    configs = {c.key: c.value for c in db.exec(select(SiteConfig)).all()}
    for key, val in DEFAULT_CONFIGS.items():
        configs.setdefault(key, val)
    CONFIG_CACHE = configs
    return configs


def cfg(key: str) -> str:
    """模板里用的配置读取函数：{{ cfg('hero_title') }}"""
    return CONFIG_CACHE.get(key, DEFAULT_CONFIGS.get(key, ""))


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    # 启动时加载全站配置到缓存
    with Session(engine) as db:
        load_config(db)
    yield


app = FastAPI(title="My Blog", lifespan=lifespan)
# Gzip 压缩（减少网络传输体积）
app.add_middleware(GZipMiddleware, minimum_size=1000)
# Session Cookie：SameSite=Lax 防 CSRF（HttpOnly 默认开启）
app.add_middleware(SessionMiddleware, secret_key=SESSION_KEY, same_site="lax", max_age=86400 * 7)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.middleware("http")
async def add_cache_header(request: Request, call_next):
    """静态资源强缓存 + 媒体文件跳过 Gzip（否则 Range 流式播放会坏）"""
    path = request.url.path
    is_media = path.startswith(("/static/audio/", "/static/covers/", "/static/assets/", "/static/img/", "/static/fonts/"))
    if is_media:
        # 去掉 Accept-Encoding，内层 GZip 中间件就不会压缩媒体（保持原始字节 + Range 支持）
        request.scope["headers"] = [
            (k, v) for k, v in request.scope["headers"] if k.lower() != b"accept-encoding"
        ]
    response = await call_next(request)
    if path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


# 自定义 404：迷失在晨雾中
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse(
            request=request, name="404.html",
            context={"admin": is_logged_in(request)}, status_code=404)
    return HTMLResponse(str(exc.detail), status_code=exc.status_code)
templates = Jinja2Templates(directory=BASE_DIR / "templates")
# 模板全局函数：{{ cfg('key') }} 读配置；{{ x | markdown }} 渲染 Markdown
templates.env.globals["cfg"] = cfg


def md_to_html(content: str) -> str:
    """Markdown → HTML（仅返回 HTML 字符串，供模板过滤器用）"""
    md_obj = md.Markdown(extensions=["fenced_code", "tables", "toc"])
    return md_obj.convert(content or "")


templates.env.filters["markdown"] = md_to_html


# ---------- 工具函数 ----------
def get_db():
    with Session(engine) as session:
        yield session


# 上传白名单：只允许图片类型（防脚本注入）
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def allowed_image(filename: str | None) -> bool:
    return bool(filename) and Path(filename).suffix.lower() in ALLOWED_IMAGE_EXT


def render_markdown(content: str) -> tuple[str, list]:
    """Markdown 正文 → HTML + 目录 tokens（toc 扩展会给标题自动加锚点 id）"""
    md_obj = md.Markdown(extensions=["fenced_code", "tables", "toc"])
    html = md_obj.convert(content or "")
    return html, getattr(md_obj, "toc_tokens", [])


def post_summary(content: str, limit: int = 80) -> str:
    """从 Markdown 正文提取纯文本摘要（去掉符号、合并空白）"""
    text = re.sub(r"[#*`>_\[\]()!-]", "", content or "")
    return " ".join(text.split())[:limit]


def first_tag(tags: str) -> str:
    """取第一个标签作为分类，没有就默认「随笔」"""
    if tags and tags.strip():
        return tags.split(",")[0].strip()
    return "随笔"


def split_tags(tags: str) -> list[str]:
    """把逗号分隔的 tags 拆成列表（过滤空项）"""
    return [t.strip() for t in (tags or "").split(",") if t.strip()]


def save_cover(cover: UploadFile | None) -> str:
    """保存上传的封面图（自动压缩转 WebP），返回可访问路径；没传/类型不合法就返回空字符串"""
    if cover is None or not allowed_image(cover.filename):
        return ""
    name = f"{uuid.uuid4().hex}.webp"  # 随机文件名，统一转 WebP
    save_optimized_image(cover.file.read(), COVERS_DIR / name)
    return f"/static/covers/{name}"


def save_optimized_image(file_bytes: bytes, target_path: Path, max_width: int = 1920, quality: int = 80):
    """用 Pillow 压缩并转码为 WebP：超宽缩放 + 高质量压缩"""
    try:
        img = Image.open(io.BytesIO(file_bytes))
        if img.width > max_width:
            height = int((max_width / img.width) * img.height)
            img = img.resize((max_width, height), Image.Resampling.LANCZOS)
        img = img.convert("RGB")
        img.save(target_path, "WEBP", quality=quality, optimize=True)
    except Exception:
        # 解析失败（如非图片文件）则原样写入，避免上传报错
        target_path.write_bytes(file_bytes)


# ---------- 前台 ----------
@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    posts = db.exec(select(Post).order_by(Post.created_at.desc())).all()
    items = make_items(posts)
    # 右侧卡片：最新一条「说说」（跳过已在大卡片/第二卡片展示的文章）
    latest_moment = next(
        (make_item(p) for p in posts[2:] if "说说" in (p.tags or "")), None)
    # 数字花园画廊：有封面的文章（排除大卡片那篇，避免重复）
    hero_id = posts[0].id if posts else -1
    gallery = [
        {"cover": p.cover_image, "title": p.title,
         "date": p.created_at.strftime("%Y.%m")}
        for p in posts if p.cover_image and p.id != hero_id
    ][:4]
    return templates.TemplateResponse(
        request=request, name="index.html",
        context={"items": items, "latest_moment": latest_moment,
                 "gallery": gallery, "admin": is_logged_in(request)},
    )


@app.get("/post/{post_id}", response_class=HTMLResponse)
def post_detail(post_id: int, request: Request, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    content_html, toc_tokens = render_markdown(post.content)
    comments = db.exec(
        select(Comment).where(Comment.post_id == post_id)
        .order_by(Comment.created_at.asc())).all()
    return templates.TemplateResponse(
        request=request, name="post.html",
        context={"post": post, "content_html": content_html,
                 "toc_tokens": toc_tokens, "category": first_tag(post.tags),
                 "comments": comments, "seo_summary": post_summary(post.content, 120),
                 "admin": is_logged_in(request)},
    )


# ---------- 独立页面：文章 / 随笔 / 关于 ----------
def make_item(p: Post) -> dict:
    """把单个 Post 包装成 {post, summary, category, read_min}"""
    return {
        "post": p,
        "summary": post_summary(p.content),
        "category": first_tag(p.tags),
        "read_min": max(1, round(len(p.content or "") / 400)),
    }


def make_items(posts):
    """把 Post 列表批量包装"""
    return [make_item(p) for p in posts]


@app.get("/articles", response_class=HTMLResponse)
def articles(request: Request, db: Session = Depends(get_db)):
    """文章页：全部文章 + 分类统计（供筛选栏）"""
    posts = db.exec(select(Post).order_by(Post.created_at.desc())).all()
    items = make_items(posts)
    # 分类计数：按全部标签拆分统计（多标签文章每个标签都计数）
    tag_counter = Counter(t for p in posts for t in split_tags(p.tags))
    categories = [{"name": name, "count": cnt} for name, cnt in tag_counter.most_common()]
    return templates.TemplateResponse(
        request=request, name="articles.html",
        context={"items": items, "categories": categories,
                 "total": len(posts), "admin": is_logged_in(request)},
    )


@app.get("/notes", response_class=HTMLResponse)
def notes(request: Request, db: Session = Depends(get_db)):
    """随笔页：只显示标签含「随笔」的文章"""
    posts = db.exec(select(Post).order_by(Post.created_at.desc())).all()
    notes_only = [p for p in posts if "随笔" in (p.tags or "")]
    return templates.TemplateResponse(
        request=request, name="notes.html",
        context={"items": make_items(notes_only), "admin": is_logged_in(request)},
    )


@app.get("/about", response_class=HTMLResponse)
def about(request: Request):
    """关于页：自我介绍"""
    return templates.TemplateResponse(
        request=request, name="about.html",
        context={"admin": is_logged_in(request)},
    )


@app.get("/moments", response_class=HTMLResponse)
def moments(request: Request, db: Session = Depends(get_db)):
    """说说页：只显示标签含「说说」的内容（轻量气泡流）"""
    posts = db.exec(select(Post).order_by(Post.created_at.desc())).all()
    moments_only = [p for p in posts if "说说" in (p.tags or "")]
    return templates.TemplateResponse(
        request=request, name="moments.html",
        context={"items": make_items(moments_only), "admin": is_logged_in(request)},
    )


# ---------- 后台 ----------
@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    if not is_logged_in(request):
        return templates.TemplateResponse(
            request=request, name="admin.html", context={"logged_in": False})
    posts = db.exec(select(Post).order_by(Post.created_at.desc())).all()
    # 统计卡片数据：全部 / 说说 / 随笔
    stats = {
        "total": len(posts),
        "moments": sum(1 for p in posts if "说说" in (p.tags or "")),
        "notes": sum(1 for p in posts if "随笔" in (p.tags or "")),
    }
    config = load_config(db)
    # 私人网盘文件列表（带人类可读大小）
    files = db.exec(select(StoredFile).order_by(StoredFile.created_at.desc())).all()
    cloud_files = [
        {"id": f.id, "original_name": f.original_name, "file_type": f.file_type,
         "file_size_formatted": format_file_size(f.file_size),
         "is_public": f.is_public,
         "created_at": f.created_at}
        for f in files
    ]
    return templates.TemplateResponse(
        request=request, name="admin.html",
        context={"logged_in": True, "posts": posts, "stats": stats,
                 "config": config, "cloud_files": cloud_files,
                 "ai_status": _ai_status()},
    )


def _ai_status():
    """AI 模块健康状态（懒加载，失败不影响后台）"""
    try:
        from ai_recipe import rag
        return rag.status()
    except Exception:
        return {"configured": False, "index_exists": False, "last_error": None}


@app.post("/admin/login")
def admin_login(request: Request, username: str = Form(...), password: str = Form(...)):
    if do_login(request, username, password):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        request=request, name="admin.html",
        context={"logged_in": False, "error": "用户名或密码错误"},
    )


@app.post("/admin/logout")
def admin_logout(request: Request):
    do_logout(request)
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/config/update")
def update_site_config(
    request: Request,
    hero_title: str = Form(...),
    hero_subtitle: str = Form(""),
    about_title: str = Form(""),
    about_bio: str = Form(""),
    site_name: str = Form(""),
    github_url: str = Form(""),
    bgm_url: str = Form(""),
    bgm_title: str = Form(""),
    bgm_lyric: str = Form(""),
    hero_bg_file: UploadFile | None = File(None),
    about_avatar_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """保存全站配置（文本 + 图片上传）"""
    if not is_logged_in(request):
        return RedirectResponse("/admin", status_code=303)

    to_update = {
        "hero_title": hero_title.strip(),
        "hero_subtitle": hero_subtitle.strip(),
        "about_title": about_title.strip(),
        "about_bio": about_bio.strip(),
        "site_name": site_name.strip(),
        "github_url": github_url.strip(),
        "bgm_url": bgm_url.strip(),
        "bgm_title": bgm_title.strip(),
        "bgm_lyric": bgm_lyric.strip(),
    }

    # 上传的新首页背景图（自动压缩转 WebP，类型白名单）
    if hero_bg_file and allowed_image(hero_bg_file.filename):
        name = f"bg_{uuid.uuid4().hex[:8]}.webp"
        save_optimized_image(hero_bg_file.file.read(), COVERS_DIR / name)
        to_update["hero_bg_image"] = f"/static/covers/{name}"

    # 上传的新头像（自动压缩转 WebP，类型白名单）
    if about_avatar_file and allowed_image(about_avatar_file.filename):
        name = f"avatar_{uuid.uuid4().hex[:8]}.webp"
        save_optimized_image(about_avatar_file.file.read(), COVERS_DIR / name)
        to_update["about_avatar"] = f"/static/covers/{name}"

    # 写入数据库（存在则更新，不存在则新建）
    for k, v in to_update.items():
        row = db.get(SiteConfig, k)
        if row:
            row.value = v
            db.add(row)
        else:
            db.add(SiteConfig(key=k, value=v))
    db.commit()
    load_config(db)  # 刷新缓存，前台立即生效
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin/new", response_class=HTMLResponse)
def admin_new(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        request=request, name="admin_form.html", context={"post": None})


@app.post("/admin/new")
def admin_create(
    request: Request,
    title: str = Form(...),
    tags: str = Form(""),
    content: str = Form(""),
    cover: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    if not is_logged_in(request):
        return RedirectResponse("/admin", status_code=303)
    post = Post(title=title, slug=title, tags=tags,
                content=content, cover_image=save_cover(cover))
    db.add(post)
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin/edit/{post_id}", response_class=HTMLResponse)
def admin_edit(post_id: int, request: Request, db: Session = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse("/admin", status_code=303)
    post = db.get(Post, post_id)
    if post is None:
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        request=request, name="admin_form.html", context={"post": post})


@app.post("/admin/edit/{post_id}")
def admin_update(
    post_id: int,
    request: Request,
    title: str = Form(...),
    tags: str = Form(""),
    content: str = Form(""),
    cover: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    if not is_logged_in(request):
        return RedirectResponse("/admin", status_code=303)
    post = db.get(Post, post_id)
    if post is None:
        return RedirectResponse("/admin", status_code=303)
    post.title = title
    post.slug = title
    post.tags = tags
    post.content = content
    new_cover = save_cover(cover)
    if new_cover:
        post.cover_image = new_cover
    db.add(post)
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/delete/{post_id}")
def admin_delete(post_id: int, request: Request, db: Session = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse("/admin", status_code=303)
    post = db.get(Post, post_id)
    if post:
        db.delete(post)
        db.commit()
    return RedirectResponse("/admin", status_code=303)


# ---------- 私人网盘（刷机备份） ----------
@app.post("/admin/storage/upload")
def upload_personal_file(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传文件到私人备份库（仅后台）"""
    if not is_logged_in(request):
        return RedirectResponse("/admin", status_code=303)
    if not file.filename:
        return RedirectResponse("/admin?tab=cloud", status_code=303)
    ext = Path(file.filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex[:12]}{ext}"
    contents = file.file.read()
    (PRIVATE_STORAGE_DIR / unique_name).write_bytes(contents)
    db.add(StoredFile(
        filename=unique_name,
        original_name=file.filename,
        file_size=len(contents),
        file_type=ext.replace(".", "").upper() or "FILE",
    ))
    db.commit()
    return RedirectResponse("/admin?tab=cloud", status_code=303)


@app.get("/storage/download/{file_id}")
def download_personal_file(file_id: int, request: Request, db: Session = Depends(get_db)):
    """下载/访问私人文件：公开文件任意下载，私密文件仅登录后台可下"""
    record = db.get(StoredFile, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    # 权限校验：私密文件必须管理员
    if not record.is_public and not is_logged_in(request):
        raise HTTPException(status_code=403, detail="该文件为私密资源，无权访问")
    file_path = PRIVATE_STORAGE_DIR / record.filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="磁盘文件已丢失")
    return FileResponse(file_path, filename=record.original_name,
                        media_type="application/octet-stream")


@app.post("/admin/storage/delete/{file_id}")
def delete_personal_file(file_id: int, request: Request, db: Session = Depends(get_db)):
    """删除私人文件（仅后台）"""
    if not is_logged_in(request):
        return RedirectResponse("/admin", status_code=303)
    record = db.get(StoredFile, file_id)
    if record:
        file_path = PRIVATE_STORAGE_DIR / record.filename
        if file_path.exists():
            file_path.unlink()
        db.delete(record)
        db.commit()
    return RedirectResponse("/admin?tab=cloud", status_code=303)


@app.post("/admin/storage/toggle-public/{file_id}")
def toggle_file_public(file_id: int, request: Request, db: Session = Depends(get_db)):
    """一键切换文件公开/私密（仅后台）"""
    if not is_logged_in(request):
        return RedirectResponse("/admin", status_code=303)
    record = db.get(StoredFile, file_id)
    if record:
        record.is_public = not record.is_public
        db.add(record)
        db.commit()
    return RedirectResponse("/admin?tab=cloud", status_code=303)


@app.get("/cloud", response_class=HTMLResponse)
def public_cloud_page(request: Request, db: Session = Depends(get_db)):
    """前台开放资源页：只显示公开文件"""
    public_files = db.exec(
        select(StoredFile).where(StoredFile.is_public == True)
        .order_by(StoredFile.created_at.desc())).all()
    files = [
        {"id": f.id, "original_name": f.original_name, "file_type": f.file_type,
         "file_size_formatted": format_file_size(f.file_size),
         "created_at": f.created_at}
        for f in public_files
    ]
    return templates.TemplateResponse(
        request=request, name="cloud.html",
        context={"files": files, "admin": is_logged_in(request)},
    )


# ---------- 全站搜索 API ----------
@app.get("/api/search")
def search_posts(q: str = "", db: Session = Depends(get_db)):
    """搜索文章标题/正文，返回 JSON（供搜索模态框使用）"""
    q = q.strip()
    if not q:
        return []
    statement = (
        select(Post)
        .where(or_(Post.title.contains(q), Post.content.contains(q)))
        .order_by(Post.created_at.desc())
        .limit(8)
    )
    return [
        {"id": p.id, "title": p.title, "tags": p.tags or "",
         "cover": p.cover_image or ""}
        for p in db.exec(statement).all()
    ]


# ---------- 音乐播放列表 API（自动扫描 static/audio/ 下所有 mp3 + 同名 lrc） ----------
@app.get("/api/playlist")
def get_playlist():
    audio_dir = BASE_DIR / "static" / "audio"
    tracks = []
    for mp3 in sorted(audio_dir.glob("*.mp3")):
        lrc = mp3.with_suffix(".lrc")
        title = mp3.stem
        artist = "周杰伦"
        if lrc.exists():
            try:
                text = lrc.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r"\[ar:([^\]]+)\]", text)
                if m:
                    artist = m.group(1).strip()
                m2 = re.search(r"\[ti:([^\]]+)\]", text)
                if m2 and m2.group(1).strip() and "track" not in m2.group(1).lower():
                    title = m2.group(1).strip()
            except Exception:
                pass
        tracks.append({
            "title": title, "artist": artist,
            "src": f"/static/audio/{mp3.name}",
            "lrc": f"/static/audio/{lrc.name}" if lrc.exists() else "",
            "cover": "/static/covers/cover6.png",
        })
    return tracks


# ---------- SEO：sitemap / robots ----------
@app.get("/sitemap.xml")
def sitemap(request: Request, db: Session = Depends(get_db)):
    base = str(request.base_url).rstrip("/")
    urls = [
        f"<url><loc>{base}/</loc></url>",
        f"<url><loc>{base}/articles</loc></url>",
        f"<url><loc>{base}/moments</loc></url>",
        f"<url><loc>{base}/notes</loc></url>",
        f"<url><loc>{base}/about</loc></url>",
        f"<url><loc>{base}/recipes</loc></url>",
    ]
    for p in db.exec(select(Post)).all():
        urls.append(f"<url><loc>{base}/post/{p.id}</loc></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           + "".join(urls) + "</urlset>")
    return Response(content=xml, media_type="application/xml")


@app.get("/robots.txt")
def robots():
    # 生产环境用 BLOG_BASE_URL（如 https://ziyizhang.cn），否则用本地
    base = os.getenv("BLOG_BASE_URL", "http://localhost:8000").rstrip("/")
    text = f"User-agent: *\nAllow: /\n\nSitemap: {base}/sitemap.xml\n"
    return Response(content=text, media_type="text/plain")


# ---------- 评论系统 ----------
@app.post("/post/{post_id}/comment")
def create_comment(
    post_id: int,
    request: Request,
    name: str = Form(""),
    content: str = Form(""),
    db: Session = Depends(get_db),
):
    """发表评论（昵称 + 内容）"""
    post = db.get(Post, post_id)
    if post is None:
        return HTMLResponse("404", status_code=404)
    name = name.strip()[:30] or "匿名"
    content = content.strip()[:1000]
    if content:
        db.add(Comment(post_id=post_id, name=name, content=content))
        db.commit()
    return RedirectResponse(f"/post/{post_id}#comments", status_code=303)


# ================= AI 食谱助手 + 管理界面 AI 改文章 =================
# 依赖: ai_recipe/ 模块（LangChain RAG + 提示词工程）
# 配置: .env 中 CHAT_API_KEY / EMBEDDING_API_KEY（详见 ai_recipe/config.py）

from pydantic import BaseModel  # noqa: E402


class AiAskRequest(BaseModel):
    question: str


class AiChatRequest(BaseModel):
    """v2 多轮对话：带 user_id（前端 localStorage 访客 id）就有记忆"""
    user_id: str = "anonymous"
    question: str
    role: str | None = None  # 临时指定身份：chef / nutritionist（不写回画像）


class AiRewriteRequest(BaseModel):
    text: str
    instruction: str = "润色"


@app.get("/recipes", response_class=HTMLResponse)
def recipes_page(request: Request):
    """食谱问答页面（公开）"""
    from ai_recipe import rag
    return templates.TemplateResponse(
        request=request, name="recipes.html",
        context={"ai_status": rag.status()},
    )


@app.post("/api/ai/ask")
def ai_ask(req: AiAskRequest, request: Request):
    """食谱问答 API：POST {"question": "..."} → {answer, sources}

    防护：来源校验（防跨站盗刷）→ 问题长度限制 → 并发限制 → 限流（
    匿名每 IP 30 分钟 3 次/每天 10 次；带 Bearer Token 每天 20 次）。
    """
    from ai_recipe import quota, rag

    ip = request.client.host if request.client else "unknown"
    token = quota.resolve_token(request)

    # 1. 来源校验（仅限匿名请求；带 token 的 API 调用放行）
    if not token:
        ok, msg = quota.check_origin(request)
        if not ok:
            raise HTTPException(status_code=403, detail=msg)

    # 2. 问题长度限制
    q = (req.question or "").strip()
    ok, msg = quota.check_question_len(q)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    # 3. 并发限制
    if not quota.acquire_concurrent(ip):
        raise HTTPException(status_code=429, detail="请求太密集，请等上一条回答完再问～")
    try:
        # 4. 限流（记录在放行后，无论问答成败都计入）
        allowed, msg, _remain = quota.check_quota(ip, token)
        if not allowed:
            quota.record(ip, token, False)
            raise HTTPException(status_code=429, detail=msg)
        quota.record(ip, token, True)
        try:
            return rag.ask(q)
        except RuntimeError as e:
            import logging
            logging.getLogger("ai_recipe").error("AI 问答失败: %s", e)
            raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后再试")
    finally:
        quota.release_concurrent(ip)


@app.post("/api/ai/chat")
def ai_chat(req: AiChatRequest, request: Request):
    """v2 多轮对话：记忆/画像/双身份/推荐/工具，POST {"user_id","question","role?"}

    防护与 /api/ai/ask 一致（来源校验 + 限流 + 并发控制）。
    user_id 为前端 localStorage 生成的访客 id，限制长度防滥用。
    """
    from ai_recipe import quota, rag

    ip = request.client.host if request.client else "unknown"
    token = quota.resolve_token(request)

    if not token:
        ok, msg = quota.check_origin(request)
        if not ok:
            raise HTTPException(status_code=403, detail=msg)

    q = (req.question or "").strip()
    ok, msg = quota.check_question_len(q)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    user_id = (req.user_id or "anonymous").strip()[:64]

    if not quota.acquire_concurrent(ip):
        raise HTTPException(status_code=429, detail="请求太密集，请等上一条回答完再问～")
    try:
        allowed, msg, _remain = quota.check_quota(ip, token)
        if not allowed:
            quota.record(ip, token, False)
            raise HTTPException(status_code=429, detail=msg)
        quota.record(ip, token, True)
        try:
            return rag.chat(user_id=user_id, question=q, role=req.role)
        except RuntimeError as e:
            import logging
            logging.getLogger("ai_recipe").error("AI 对话失败: %s", e)
            raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后再试")
    finally:
        quota.release_concurrent(ip)


class AiChatClearRequest(BaseModel):
    user_id: str = "anonymous"


@app.post("/api/ai/chat/clear")
def ai_chat_clear(req: AiChatClearRequest, request: Request):
    """清空某访客的对话历史（画像保留）。来源校验防跨站滥用。"""
    from ai_recipe import quota

    if not quota.resolve_token(request):
        ok, msg = quota.check_origin(request)
        if not ok:
            raise HTTPException(status_code=403, detail=msg)
    user_id = (req.user_id or "anonymous").strip()[:64]
    from ai_recipe.memory import clear_history
    clear_history(user_id)
    return {"status": "ok"}


class AiRoleRequest(BaseModel):
    user_id: str = "anonymous"
    role: str = "chef"  # chef（厨师老王）/ nutritionist（营养师小林）


@app.post("/api/ai/role")
def ai_role_switch(req: AiRoleRequest, request: Request):
    """切换身份：chef（厨师老王）/ nutritionist（营养师小林），写入访客画像（长期生效）

    body: {"user_id": "...", "role": "chef" | "nutritionist"}
    """
    from ai_recipe import quota

    if not quota.resolve_token(request):
        ok, msg = quota.check_origin(request)
        if not ok:
            raise HTTPException(status_code=403, detail=msg)

    role = (req.role or "chef").strip().lower()
    if role not in ("chef", "nutritionist"):
        raise HTTPException(status_code=400, detail="role 只能是 chef 或 nutritionist")

    from ai_recipe.memory import update_profile
    user_id = (req.user_id or "anonymous").strip()[:64]
    update_profile(user_id, role=role)
    return {"status": "ok", "role": role}


@app.get("/api/ai/role/{user_id}")
def ai_role_get(user_id: str, request: Request):
    """查询当前身份（前端加载时同步按钮状态）"""
    from ai_recipe.memory import get_profile
    return {"role": get_profile(user_id.strip()[:64]).get("role", "chef")}


@app.get("/api/ai/quota")
def ai_quota(request: Request):
    """AI 用量统计（后台 AI 助手面板，需登录）"""
    if not is_logged_in(request):
        raise HTTPException(status_code=403, detail="请先登录后台")
    from ai_recipe import quota
    return quota.today_stats()


@app.post("/api/ai/rewrite")
def ai_rewrite(req: AiRewriteRequest, request: Request):
    """管理界面 AI 改文章：润色/扩写/精简/起标题（需登录）"""
    if not is_logged_in(request):
        raise HTTPException(status_code=403, detail="请先登录后台")
    from ai_recipe import rewrite as ai_rw
    try:
        return {"text": ai_rw.rewrite(req.text, req.instruction)}
    except RuntimeError as e:
        import logging
        logging.getLogger("ai_recipe").error("AI 润色失败: %s", e)
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后再试")


@app.post("/api/ai/ingest")
def ai_ingest(request: Request):
    """重建食谱索引（管理界面按钮调用，需登录）"""
    if not is_logged_in(request):
        raise HTTPException(status_code=403, detail="请先登录后台")
    from ai_recipe import rag
    return rag.rebuild()


@app.post("/api/ai/upload")
def ai_upload(request: Request, file: UploadFile = File(...)):
    """上传文档到食谱库（PDF/docx/txt/md，自动解析向量化，需登录）"""
    if not is_logged_in(request):
        raise HTTPException(status_code=403, detail="请先登录后台")
    from ai_recipe import rag

    data = file.file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件超过 20MB 限制")
    try:
        md_text = rag.parse_upload_to_markdown(file.filename or "", data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # PDF 损坏 / 扫描件等解析失败：友好提示而不是 500
        raise HTTPException(status_code=400, detail=f"文档解析失败（{type(e).__name__}），PDF 可能是扫描件或已损坏")
    if not md_text:
        raise HTTPException(status_code=400, detail="文档解析后没有内容（PDF 可能是扫描件/图片）")

    # 同名覆盖：先删旧文件，再写新文件
    name = Path(file.filename or "未命名.md").stem
    rag.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = rag.UPLOAD_DIR / f"{name}.md"
    target.write_text(md_text, encoding="utf-8")
    rag.rebuild()
    return {"status": "ok", "message": f"已上传 {file.filename}（{len(md_text)} 字符），索引已更新", "path": target.name}


@app.get("/api/ai/docs")
def ai_docs(request: Request):
    """食谱库文档列表（需登录）"""
    if not is_logged_in(request):
        raise HTTPException(status_code=403, detail="请先登录后台")
    from ai_recipe import rag
    return {"docs": rag.list_docs(), "total": len(rag.list_docs())}


@app.post("/api/ai/doc/delete")
def ai_doc_delete(request: Request, body: dict):
    """删除上传的文档（需登录）"""
    if not is_logged_in(request):
        raise HTTPException(status_code=403, detail="请先登录后台")
    from ai_recipe import rag
    rel = (body or {}).get("path", "")
    if not rel:
        raise HTTPException(status_code=400, detail="缺少 path 参数")
    try:
        return rag.delete_doc(rel)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
