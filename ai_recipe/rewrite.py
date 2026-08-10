"""管理界面「AI 修改文章」：润色 / 扩写 / 精简 / 起标题"""
from .config import settings
from .prompt import REWRITE_PROMPT


def rewrite(text: str, instruction: str = "润色") -> str:
    """按指令修改文本，返回修改后的完整文本"""
    if not settings.chat_api_key:
        raise RuntimeError("AI 未配置：请在 .env 中设置 CHAT_API_KEY")
    if not text or not text.strip():
        raise RuntimeError("内容为空，请先输入正文")

    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.chat_api_key,
        base_url=settings.chat_base_url,
        temperature=0.5,
        max_tokens=3000,
        timeout=90,
    )
    resp = llm.invoke([
        ("system", "你是资深中文博客写作编辑。"),
        ("human", REWRITE_PROMPT.format(instruction=instruction, text=text)),
    ])
    return (resp.content or "").strip()
