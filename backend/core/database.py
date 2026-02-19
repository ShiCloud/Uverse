"""
数据库配置 - PostgreSQL + Pgvector
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker

# 导入公共配置
from utils import DatabaseConfig

# 全局变量
engine = None
AsyncSessionLocal = None
Base = declarative_base()


def init_engine():
    """初始化数据库引擎。在应用启动时调用，确保环境变量已设置。"""
    global engine, AsyncSessionLocal
    
    # 使用 DatabaseConfig 构建连接 URL
    database_url = DatabaseConfig.get_connection_url()
    
    # 创建异步引擎 - echo=False 避免日志干扰
    engine = create_async_engine(database_url, echo=False)
    
    # 会话工厂
    AsyncSessionLocal = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    return engine


def get_engine():
    """获取数据库引擎，如果未初始化则自动初始化。"""
    if engine is None:
        return init_engine()
    return engine


def get_session_local():
    """获取会话工厂，如果未初始化则自动初始化。"""
    if AsyncSessionLocal is None:
        init_engine()
    return AsyncSessionLocal


async def get_db():
    """获取数据库会话"""
    SessionLocal = get_session_local()
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """初始化数据库表"""
    eng = get_engine()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
