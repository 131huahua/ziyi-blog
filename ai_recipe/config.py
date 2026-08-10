"""AI 配置：从 .env 环境变量读取

- 对话：OpenAI 兼容 API（DeepSeek / 硅基流动 / NVIDIA 等任选）
- 向量：默认本地 fastembed（BAAI/bge-small-zh-v1.5，离线免费）；也可配 API
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


class Settings:
    # 对话模型
    chat_api_key: str = os.getenv("CHAT_API_KEY", "")
    chat_base_url: str = os.getenv("CHAT_BASE_URL", "https://api.deepseek.com/v1")
    chat_model: str = os.getenv("CHAT_MODEL", "deepseek-chat")
    temperature: float = float(os.getenv("TEMPERATURE", "0.4"))
    max_tokens: int = int(os.getenv("MAX_TOKENS", "2000"))

    # 对话 fallback（主模型失败时自动切换，如智谱 glm-4-flash 免费额度）
    fallback_chat_api_key: str = os.getenv("FALLBACK_CHAT_API_KEY", "")
    fallback_chat_base_url: str = os.getenv("FALLBACK_CHAT_BASE_URL", "")
    fallback_chat_model: str = os.getenv("FALLBACK_CHAT_MODEL", "")

    # 向量模型
    # EMBEDDING_PROVIDER=local → 本地 fastembed（离线免费，推荐）
    # EMBEDDING_PROVIDER=api   → 用下面的 API 配置
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "local")
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY", "")
    embedding_base_url: str = os.getenv("EMBEDDING_BASE_URL", "")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")

    # 记忆
    memory_db_path: str = os.getenv(
        "MEMORY_DB_PATH", str(Path(__file__).resolve().parent.parent / "memory.db")
    )
    history_limit: int = int(os.getenv("HISTORY_LIMIT", "8"))

    @property
    def ready(self) -> bool:
        """对话需要 chat key；embedding 本地模式不需要 key"""
        if not self.chat_api_key:
            return False
        if self.embedding_provider == "local":
            return True
        return bool(self.embedding_api_key)


settings = Settings()
