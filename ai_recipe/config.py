"""AI 配置：从 .env 环境变量读取，默认指向硅基流动（一个 key 搞定对话+向量）"""
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
    chat_base_url: str = os.getenv("CHAT_BASE_URL", "https://api.siliconflow.cn/v1")
    chat_model: str = os.getenv("CHAT_MODEL", "deepseek-ai/DeepSeek-V4-Flash")

    # 向量模型（embedding）
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY", "")
    embedding_base_url: str = os.getenv("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

    @property
    def ready(self) -> bool:
        return bool(self.chat_api_key and self.embedding_api_key)


settings = Settings()
