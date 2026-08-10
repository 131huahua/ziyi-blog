# ZIYI 的博客 🌲

> 晨雾森林美学 · FastAPI + Jinja2 服务端渲染 · 从零手写

一个在深邃松林与晨雾中记录代码与生活的个人博客。全站由 Python 从零构建，无前端框架，主打封面视觉、液态玻璃动效与沉浸式音乐体验。

**🔗 线上地址：https://ziyizhang.cn**

---

## ✨ 功能特性

### 🎨 视觉与动效
- **晨雾美学**：雾森壁纸 + 液态玻璃（Glassmorphism）+ 留白排版
- **日夜双模**：白天晨雾奶白 ↔ 黑夜松林翡翠，☀️/🌙 秒切，防闪烁（Anti-FART）
- **影院级首页**：鼠标视差、晨雾呼吸光晕、级联拉焦涌现、流光渐变标题、3D 卡片倾斜 + 液态扫光
- **开屏动画**：HELLO ZIYI 晨雾消散（仅首页首次访问）
- **HTMX 软导航**：切页内容区平滑过渡，顶栏与播放器 DOM 常驻

### 🎵 音乐系统
- 13 首周杰伦精选（FLAC → 192kbps MP3）
- 顶栏微缩胶囊 + Apple Music 风格大播放器
- 逐句歌词滚动高亮（GBK → UTF-8 自动转码）
- 跨页续播：切页不中断，刷新恢复进度（sessionStorage）
- `/api/playlist` 自动扫描 `static/audio/`，放文件即上架

### 📝 内容板块
- **首页**：精选文章 + 个人状态 + 数字花园画廊 + 技术栈
- **文章**：卡片流 + 分类筛选 + 实时搜索（Ctrl/⌘+K 全局搜索）
- **说说**：双列社交卡片流 + 心情标签 + 点赞
- **随笔**：时间轴 + 玻璃卡片
- **开放资源**：私人网盘公开分享页
- **关于**：个人介绍

### 💾 私人网盘
- 后台上传 / 下载 / 删除，中文文件名支持
- 公开/私密切换，私密文件 403 保护
- 前台 `/cloud` 开放资源页

### ⚙️ 全站可配置（后台）
- 站点名、首页文案、背景图、关于页、GitHub 链接
- BGM 歌曲、歌词、封面
- 后台多 Tab：文章管理 / 站点设置 / 私人网盘

### 🚀 工程与性能
- FastAPI + Jinja2 SSR，SQLModel + SQLite（可切 PostgreSQL）
- Markdown 写作 + 代码高亮（Prism）+ 一键复制
- Gzip 压缩（媒体路径豁免，Range 流式播放正常）
- 静态资源 immutable 缓存 + WebP 图片压缩
- 自定义 404「LOST IN THE MIST」+ sitemap + robots + OG Meta

---

## 🛠️ 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python · FastAPI · SQLModel · Jinja2 |
| 前端 | Tailwind CSS · HTMX · 原生 JS（无框架） |
| 数据库 | SQLite（开发）/ PostgreSQL（生产） |
| 部署 | uvicorn · systemd · Nginx · Let's Encrypt |

---

## 🚀 本地运行

```bash
# 1. 克隆
git clone https://github.com/131huahua/ziyi-blog.git
cd ziyi-blog

# 2. 虚拟环境
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

# 3. 依赖
pip install -r requirements.txt

# 4. 初始化演示数据（可选）
python seed.py

# 5. 启动
uvicorn main:app --reload
```

打开 http://localhost:8000 ，后台 http://localhost:8000/admin

> 默认管理员 admin / admin123 —— **上线前务必改掉！**（见下方生产配置）

---

## 🤖 AI 食谱助手（v2：双身份 + 记忆 + 推荐 + 工具）

食谱页 `/recipes` 的 AI 只回答做饭问题，v2 能力：

- **双身份**：默认「厨师老王」；提到减脂/控糖/增肌自动切「营养师小林」（写入访客画像），说「切回厨师」恢复
- **推荐模式**：问「吃什么/推荐」返回菜谱 + `why`（为什么推荐）+ `how`（怎么做省事）
- **记忆**：SQLite 存用户画像（口味/忌口/健康目标自动学习）+ 最近 8 轮对话；按访客 id（前端 localStorage）隔离
- **工具**：本地实现热量估算/时令食材/单位换算/营养建议（模型输出 tool_calls → 系统执行 → 再回答）
- **本地向量**：默认 fastembed（bge-small-zh，离线免费，首次运行自动下载，国内走 hf-mirror）

### AI 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/ai/chat` | v2 多轮对话，body: `{"user_id", "question", "role?"}` |
| POST | `/api/ai/ask` | v1 单轮问答（兼容） |
| POST | `/api/ai/chat/clear` | 清空某访客对话历史 |
| POST | `/api/ai/ingest` | 重建食谱索引（新增/修改 `recipes/` 后调用，需登录后台） |
| POST | `/api/ai/upload` | 上传 PDF/docx/txt/md 入库（需登录后台） |
| POST | `/api/ai/rewrite` | 管理界面 AI 改文章（需登录后台） |
| GET | `/api/ai/quota` | AI 用量统计（需登录后台） |

### 部署注意

1. **换 embedding 模型必须重建索引**：`curl -X POST https://你的域名/api/ai/ingest`（或后台按钮）。代码会自动检测 collection 缺失/维度不匹配
2. 本地 embedding 模型首次运行自动下载（约 100MB）；服务器无外网或想离线，可先在本地跑一次再传 `~/.cache` 或设置 `HF_HOME`
3. 记忆库默认 `memory.db`（自动创建），备份时一并备份；访客数据量很小，无需清理
4. 微调可选：`ai_recipe/` 配套脚本 `scripts/build_finetune_data.py` + 教程见 repo 根目录 `finetune/README.md`（LLaMA-Factory + Qwen2.5 LoRA）

---

## 🚀 生产部署

### 环境变量（`.env`）

```bash
# 数据库（PostgreSQL 示例）
BLOG_DB_URL=postgresql://user:pass@localhost:5432/blog

# 后台账号
BLOG_ADMIN_USER=your_account
BLOG_ADMIN_PASS_HASH=<sha256 of password>   # python -c "import hashlib; print(hashlib.sha256(b'pass').hexdigest())"

# 会话密钥（随机生成）
SESSION_KEY=<random 64 hex>

# 站点基础 URL（用于 sitemap/robots）
BLOG_BASE_URL=https://ziyizhang.cn
```

### systemd（`blog.service` 示例）

```ini
[Unit]
Description=ZIYI Blog
After=network.target postgresql.service

[Service]
Type=simple
WorkingDirectory=/opt/blog
EnvironmentFile=/opt/blog/.env
ExecStart=/opt/blog/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always

[Install]
WantedBy=multi-user.target
```

### Nginx 要点

```nginx
location /static/ {
    alias /opt/blog/static/;
    expires 30d;
    add_header Cache-Control "public, immutable";
}
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

---

## 📁 目录结构

```
ziyi-blog/
├── main.py                    # 路由 / 中间件 / 配置缓存
├── models.py                  # 数据模型 + 默认配置
├── auth.py                    # 后台登录（sha256）
├── database.py                # SQLite / PostgreSQL 切换
├── seed.py                    # 演示数据
├── ai_recipe/                 # 🤖 食谱 AI（v2：RAG + 双身份 + 记忆 + 工具）
│   ├── rag.py                 # 多轮对话：检索→记忆→工具调度→推荐
│   ├── prompt.py              # 提示词工程：厨师老王/营养师小林 + 拒答规则
│   ├── memory.py              # SQLite 用户画像 + 对话历史
│   ├── tools.py               # 本地工具：热量/时令/换算/营养
│   ├── quota.py               # 接口防护：限流/来源校验/并发
│   ├── rewrite.py             # 文章润色
│   └── config.py              # 从 .env 读配置
├── recipes/                   # 📚 食谱库（markdown，放文件后重建索引）
├── chroma_db/                 # 向量库（自动生成）
├── memory.db                  # 记忆库（自动生成）
├── templates/
│   ├── base.html              # 基础模板（双模 + 防闪烁）
│   ├── components/
│   │   └── navbar_player.html # 顶栏 + 音乐播放器组件
│   ├── index.html             # 首页（影院级 Hero）
│   ├── articles.html          # 文章列表
│   ├── moments.html           # 说说
│   ├── notes.html             # 随笔
│   ├── cloud.html             # 开放资源
│   ├── about.html             # 关于
│   └── post.html              # 文章详情
├── static/
│   ├── css/style.css          # 全站样式与动效
│   ├── js/main.js             # 交互逻辑
│   ├── audio/                 # 音乐（放文件即上架）
│   └── covers/                # 封面图
└── requirements.txt
```

---

## 📜 版权说明

- 音乐文件（`static/audio/`）版权归原作者所有，仅用于个人学习演示，请勿商用
- 背景壁纸素材版权归原作者所有
- 代码基于 MIT 精神开源，欢迎学习参考

---

## 📬 联系

- GitHub: [@131huahua](https://github.com/131huahua)
- 博客: https://ziyizhang.cn

---

*Build with ❤️ by ZIYI — 雾起时开始，雾散时上线。*
