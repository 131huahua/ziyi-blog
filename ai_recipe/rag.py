"""LangChain RAG v2：检索 → 记忆注入 → 工具调度 → 推荐回答

保留 v1 功能：上传文档解析 / 文档管理 / 重建索引 / 健康状态
新增 v2 功能：多轮对话 chat()（记忆+画像+双身份+工具）、本地 embedding
"""
import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("ai_recipe")

BASE_DIR = Path(__file__).resolve().parent.parent
RECIPES_DIR = BASE_DIR / "recipes"
UPLOAD_DIR = RECIPES_DIR / "上传文档"
CHROMA_DIR = BASE_DIR / "chroma_db"

_llm = None
_fallback_llm = None
_vectorstore = None
_last_error: str | None = None

# 角色切换关键词 → 切换后身份
ROLE_KEYWORDS = {
    "nutritionist": ["营养师", "减脂", "控糖", "减肥", "增肌", "健身餐", "卡路里", "热量低", "低卡"],
}
BACK_TO_CHEF_KEYWORDS = ["切回厨师", "变回厨师", "还是厨师", "厨师模式"]

# 画像自动学习关键词
LEARN_RULES = [
    (re.compile(r"不(吃|喜欢|要|沾)([^，。！？\s,.;!?]{1,8})"), "忌口", "capture2"),
    (re.compile(r"对([^，。！？\s,.;!?]{1,8})过敏"), "忌口", "capture1"),
    (re.compile(r"(减肥|减脂|控糖|增肌|健身|低卡|清淡饮食)"), "健康目标", "fixed"),
    (re.compile(r"(喜欢|爱吃)(吃)?([^，。！？\s,.;!?]{1,4})口味"), "口味偏好", "capture3"),
]


# ---------- 上传文档解析 ----------

def parse_upload_to_markdown(filename: str, data: bytes) -> str:
    """把上传的 PDF/docx/txt/md 解析成 Markdown 文本（供 RAG 入库）"""
    import io
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages = [(p.extract_text() or "") for p in reader.pages]
        return "\n\n".join(pages).strip()
    if ext == ".docx":
        from docx import Document
        doc = Document(io.BytesIO(data))
        lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(lines)
    if ext in (".md", ".markdown", ".txt"):
        return data.decode("utf-8", errors="ignore").strip()
    raise ValueError(f"不支持的文件类型 {ext}，仅支持 pdf / docx / md / txt")


def list_docs() -> list[dict]:
    """列出食谱库全部文档（含上传文档）"""
    docs = []
    for f in sorted(RECIPES_DIR.rglob("*.md")):
        rel = f.relative_to(RECIPES_DIR).as_posix()
        docs.append({
            "path": rel,
            "name": f.name,
            "size": f.stat().st_size,
            "is_upload": UPLOAD_DIR in f.parents,
        })
    return docs


def delete_doc(rel_path: str) -> dict:
    """删除食谱库文档（仅允许删除上传文档，防删库文件）"""
    target = (RECIPES_DIR / rel_path).resolve()
    if not target.is_file() or not str(target).startswith(str(RECIPES_DIR.resolve())):
        raise ValueError("文件不存在")
    if not str(target).startswith(str(UPLOAD_DIR.resolve())):
        raise ValueError("只能删除上传的文档")
    target.unlink()
    _get_vectorstore(force_rebuild=True)
    return {"status": "ok", "message": f"已删除 {rel_path} 并重建索引"}


# ---------- 模型 ----------

def _get_llm(use_fallback: bool = False):
    """对话模型（OpenAI 兼容）。use_fallback=True 返回备胎模型（如智谱免费 glm-4-flash）"""
    from langchain_openai import ChatOpenAI
    from .config import settings

    global _llm, _fallback_llm
    if use_fallback:
        if _fallback_llm is None and settings.fallback_chat_api_key:
            _fallback_llm = ChatOpenAI(
                model=settings.fallback_chat_model,
                api_key=settings.fallback_chat_api_key,
                base_url=settings.fallback_chat_base_url,
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                timeout=60,
            )
        return _fallback_llm

    if _llm is None:
        _llm = ChatOpenAI(
            model=settings.chat_model,
            api_key=settings.chat_api_key,
            base_url=settings.chat_base_url,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            timeout=60,
        )
    return _llm


def _get_embeddings():
    """向量模型：默认本地 fastembed（离线免费）；配了 EMBEDDING_API_KEY 才走 API"""
    from .config import settings

    if settings.embedding_provider == "local":
        # 国内网络：默认走 hf-mirror 镜像下载模型；禁用 xet 协议（镜像不支持，会 401）
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        from langchain_community.embeddings import FastEmbedEmbeddings
        return FastEmbedEmbeddings(model_name=settings.embedding_model)

    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
        timeout=30,
        max_retries=1,
    )


# ---------- 索引 ----------

def _load_and_split():
    """读取 recipes/ 下所有 .md 食谱文件并切块"""
    from langchain_community.document_loaders import DirectoryLoader, TextLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    loader = DirectoryLoader(
        str(RECIPES_DIR),
        glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    docs = loader.load()
    if not docs:
        raise RuntimeError(f"recipes/ 目录下没有找到任何 .md 文件，请先放入食谱。目录: {RECIPES_DIR}")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
    )
    return splitter.split_documents(docs)


def _get_vectorstore(force_rebuild: bool = False):
    """获取向量库；首次运行自动建库，之后直接加载"""
    global _vectorstore
    from langchain_chroma import Chroma
    import chromadb

    if _vectorstore is not None and not force_rebuild:
        return _vectorstore

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection_names = {c.name for c in client.list_collections()}
    needs_rebuild = force_rebuild or "recipes" not in collection_names

    if needs_rebuild:
        # 删除旧 collection（embedding 模型更换后维度可能不匹配）
        try:
            client.delete_collection("recipes")
        except Exception:
            pass
        docs = _load_and_split()
        _vectorstore = Chroma.from_documents(
            docs, _get_embeddings(),
            client=client, collection_name="recipes",
        )
        logger.info("食谱索引已建立：%d 个片段", len(docs))
    else:
        _vectorstore = Chroma(
            client=client, collection_name="recipes",
            embedding_function=_get_embeddings(),
        )
    return _vectorstore


# ---------- v2 多轮对话 ----------

def _sanitize_input(text: str) -> str:
    """输入清洗：移除控制字符/零宽字符，防提示词注入变体和异常字符"""
    if not text:
        return ""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    cleaned = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff\u00ad]", "", cleaned)
    return cleaned.strip()


def _sanitize_user_id(user_id: str) -> str:
    """user_id 白名单：仅字母/数字/下划线/连字符，最长 64，非法则回退 anonymous"""
    uid = (user_id or "").strip()[:64]
    if re.fullmatch(r"[A-Za-z0-9_\-]+", uid):
        return uid
    return "anonymous"


def _source_name(source: str) -> str:
    """从路径提取文件名（兼容 Windows \\ 与 Unix / 分隔符）"""
    return str(source).replace("\\", "/").split("/")[-1]


def _detect_role(user_id: str, question: str) -> str:
    """根据用户消息自动切换身份（并写回画像）"""
    from .memory import get_profile, update_profile

    profile = get_profile(user_id)
    role = profile.get("role", "chef")

    if any(k in question for k in BACK_TO_CHEF_KEYWORDS):
        if role != "chef":
            update_profile(user_id, role="chef")
        return "chef"

    for target, keywords in ROLE_KEYWORDS.items():
        if any(k in question for k in keywords) and role != target:
            update_profile(user_id, role=target)
            return target
    return role


def _learn_from_message(user_id: str, question: str) -> None:
    """从用户反馈里自动学习画像：忌口/健康目标/口味偏好"""
    from .memory import update_profile

    learned = {}
    for pattern, field, mode in LEARN_RULES:
        m = pattern.search(question)
        if not m:
            continue
        if mode == "fixed":
            learned[field] = m.group(1)
        elif mode == "capture1":
            learned.setdefault(field, []).append(m.group(1))
        elif mode == "capture2":
            learned.setdefault(field, []).append(m.group(2))
        elif mode == "capture3":
            learned.setdefault(field, []).append(m.group(3))
    if learned:
        update_profile(user_id, **learned)


def _history_to_text(history: list[dict]) -> str:
    """把最近对话历史压成紧凑文本"""
    if not history:
        return ""
    lines = []
    for msg in history:
        role = "用户" if msg["role"] == "user" else "助手"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines)


def _is_recommend_question(question: str) -> bool:
    return any(k in question for k in ["吃什么", "推荐", "今晚", "明天", "做点", "有啥", "给我来", "安排"])


def _call_llm(messages: list) -> str:
    """调用 LLM；主模型失败时自动切 fallback（如智谱免费额度）"""
    try:
        resp = _get_llm().invoke(messages)
        return resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:
        fb = _get_llm(use_fallback=True)
        if fb is None:
            raise
        logger.warning("主模型调用失败(%s)，切换到 fallback 模型", str(e)[:100])
        resp = fb.invoke(messages)
        return resp.content if hasattr(resp, "content") else str(resp)


def chat(user_id: str, question: str, role: str | None = None) -> dict:
    """多轮对话主入口（推荐/问答/营养师模式都走这里）

    - role 参数可临时指定身份（不写回画像）；缺省时自动检测+学习
    - 返回 {"answer": {...}, "sources": [...]}
    """
    from .config import settings
    from .memory import add_message, get_history, get_profile
    from .prompt import build_system_prompt
    from .tools import run_tool
    from langchain_core.messages import HumanMessage, SystemMessage

    global _last_error
    if not settings.ready:
        _last_error = "AI 未配置：请在 .env 中设置 CHAT_API_KEY"
        raise RuntimeError(_last_error)

    try:
        # 输入清洗（防注入/防异常字符）
        user_id = _sanitize_user_id(user_id)
        question = _sanitize_input(question)
        if not question:
            raise RuntimeError("问题不能为空")

        profile = get_profile(user_id)
        if role is None:
            role = _detect_role(user_id, question)
        _learn_from_message(user_id, question)
        profile = get_profile(user_id)

        history = get_history(user_id, limit=settings.history_limit)
        vectorstore = _get_vectorstore()
        k = 6 if _is_recommend_question(question) else 4
        retriever = vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={"k": k, "fetch_k": 20, "lambda_mult": 0.7},
        )
        docs = retriever.invoke(question)
        context = "\n\n".join(d.page_content for d in docs)

        history_text = _history_to_text(history)
        system_prompt = build_system_prompt(role, profile)

        def build_messages(extra_context: str = "") -> list:
            msgs = [SystemMessage(content=system_prompt)]
            if history_text:
                msgs.append(SystemMessage(content=f"【对话历史】\n{history_text}"))
            msgs.append(HumanMessage(content=(
                f"【参考资料】\n{context}\n\n"
                f"{extra_context}\n\n"
                f"【用户问题】{question}"
            )))
            return msgs

        # 第一轮：可能输出 tool_calls，也可能直接回答
        answer_text = _call_llm(build_messages())
        parsed = _try_parse_json(answer_text)

        # 工具调度：模型要调工具 → 执行 → 结果拼回 → 第二轮
        if isinstance(parsed, dict) and parsed.get("type") == "tool_calls":
            tool_results = []
            for call in parsed.get("calls", []):
                name = call.get("name")
                args = call.get("arguments", {})
                result = run_tool(name, args)
                tool_results.append(
                    f"工具 {name}({json.dumps(args, ensure_ascii=False)}) 结果："
                    f"{json.dumps(result, ensure_ascii=False)}"
                )
            extra = "【工具执行结果】\n" + "\n".join(tool_results) + "\n\n请基于工具结果输出正式回答。"
            answer_text = _call_llm(build_messages(extra))
            parsed = _try_parse_json(answer_text)

        if parsed is None:
            fix_prompt = (
                f"你刚才的输出不是合法 JSON。请把下面内容重新整理成合法 JSON 输出，"
                f"严格遵守系统格式要求：\n{answer_text}"
            )
            fixed = _call_llm([
                SystemMessage(content=system_prompt),
                HumanMessage(content=fix_prompt),
            ])
            parsed = _try_parse_json(fixed) or {"type": "parse_error", "message": "AI 输出解析失败，请重试"}

        # 写回短期记忆
        add_message(user_id, "user", question)
        add_message(user_id, "assistant", _answer_to_text(parsed))

        return {
            "answer": parsed,
            # 来源脱敏：只返回文件名，不暴露服务器绝对路径
            "sources": sorted({_source_name(d.metadata.get("source", "")) for d in docs}),
            "role": role,
        }
    except Exception as e:
        _last_error = str(e)
        logger.exception("食谱对话失败")
        raise


def _answer_to_text(answer: dict) -> str:
    """把回答 JSON 压成一行文本存进历史"""
    t = answer.get("type", "")
    if t == "recipe":
        return f"推荐了菜谱：{answer.get('name')}"
    if t == "recipes":
        return f"推荐了菜谱：{'、'.join(answer.get('name', []))}"
    if t == "recommend":
        return f"推荐：{answer.get('name')}（{answer.get('why', '')}）"
    return answer.get("message", "")[:100]


def ask(question: str) -> dict:
    """兼容 v1 的 /api/ai/ask：单轮问答（匿名用户，无记忆）"""
    return chat(user_id="anonymous", question=question)


def rebuild() -> dict:
    """管理后台调用：新增/修改食谱后重建索引"""
    _get_vectorstore(force_rebuild=True)
    return {"status": "ok", "message": "食谱索引已重建"}


def status() -> dict:
    """健康状态（管理界面显示用）"""
    from .config import settings
    return {
        "configured": settings.ready,
        "recipes_dir": str(RECIPES_DIR),
        "index_exists": (CHROMA_DIR / "chroma.sqlite3").exists(),
        "embedding_provider": settings.embedding_provider,
        "last_error": _last_error,
    }


def _try_parse_json(text: str):
    """从模型输出中提取 JSON（容忍被 ```json 包裹的情况）"""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试截取第一个 { 到最后一个 }
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None
        return None
