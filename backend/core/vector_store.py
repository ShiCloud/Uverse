"""
向量存储配置 - Pgvector + Langchain
"""
import os
from langchain_community.vectorstores import PGVector
from langchain_openai import OpenAIEmbeddings


def get_connection_string() -> str:
    """获取数据库连接字符串"""
    # 优先使用环境变量中的 DATABASE_URL
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        # 将 asyncpg 转换为同步连接字符串
        return db_url.replace("postgresql+asyncpg://", "postgresql://")
    
    # 使用嵌入式数据库默认配置
    return "postgresql://postgres:postgres@127.0.0.1:15432/knowledge_base"


# 集合名称
COLLECTION_NAME = "documents"


def get_vector_store():
    """
    获取向量存储实例
    TODO: 配置实际的 Embedding 模型
    """
    # embeddings = OpenAIEmbeddings()
    # vector_store = PGVector(
    #     connection_string=get_connection_string(),
    #     embedding_function=embeddings,
    #     collection_name=COLLECTION_NAME,
    # )
    # return vector_store
    pass
