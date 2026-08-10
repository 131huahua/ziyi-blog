"""LangChain RAG 核心：食谱 → 切块 → 向量化 → 检索 → 生成。

懒加载设计：首次提问时才建索引，避免博客启动变慢 / 内存峰值。
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger("ai_recipe")

BASE_DIR = Path(__file__).resolve().parent.parent
RECIPES_DIR = BASE_DIR / "recipes"
CHROMA_DIR = BASE_DIR / "chroma_db"

_llm = None
_vectorstore = None
_last_error: str | None = None


def _get_llm():
    """对话模型（OpenAI 兼容）"""
    global _llm
    from langchain_openai import ChatOpenAI
    from .config import settings

    if _llm is None:
        _llm = ChatOpenAI(
            model=settings.chat_model,
            api_key=settings.chat_api_key,
            base_url=settings.chat_base_url,
            temperature=0.3,
            max_tokens=2000,
            timeout=60,
        )
    return _llm


def _get_embeddings():
    """向量模型（OpenAI 兼容，硅基流动 bge-m3 免费）"""
    from langchain_openai import OpenAIEmbeddings
    from .config import settings

    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
    )


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
    if force_rebuild or not (CHROMA_DIR / "chroma.sqlite3").exists():
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


def ask(question: str) -> dict:
    """提问入口：检索相关食谱片段 → 交给 LLM 按提示词格式回答

    返回: {"answer": <dict>, "sources": [文件名...]}
    """
    global _last_error
    from .config import settings
    from .prompt import SYSTEM_PROMPT
    from langchain_chroma import Chroma  # noqa: F401  确保依赖已安装
    from langchain_core.messages import HumanMessage, SystemMessage

    if not settings.ready:
        _last_error = "AI 未配置：请在 .env 中设置 CHAT_API_KEY 和 EMBEDDING_API_KEY"
        raise RuntimeError(_last_error)

    try:
        vectorstore = _get_vectorstore()
        retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

        from langchain_core.output_parsers import StrOutputParser

        def _format_docs(docs):
            return "\n\n".join(d.page_content for d in docs)

        # 手工构造消息（不用 ChatPromptTemplate，避免 system 提示词里的 JSON 花括号被当成模板变量）
        retrieved = retriever.invoke(question)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"【参考资料】\n{_format_docs(retrieved)}\n\n【用户问题】{question}"),
        ]
        answer_text = (_get_llm() | StrOutputParser()).invoke(messages)
        parsed = _try_parse_json(answer_text)
        if parsed is None:
            # AI 格式跑偏：重试一次，强制 JSON
            fixed = _get_llm().invoke([
                ("system", SYSTEM_PROMPT),
                ("human", f"你刚才的输出不是合法 JSON。请把下面内容重新整理成合法 JSON 输出，严格遵守系统格式要求：\n{answer_text}"),
            ])
            parsed = _try_parse_json(fixed.content) or {"type": "parse_error", "message": "AI 输出解析失败，请重试"}

        return {
            "answer": parsed,
            "sources": sorted({d.metadata.get("source", "") for d in retrieved}),
        }
    except Exception as e:
        _last_error = str(e)
        logger.exception("食谱问答失败")
        raise


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
        return None
