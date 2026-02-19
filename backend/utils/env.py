"""
环境变量工具模块 - 统一处理环境变量读取和解析
"""
import os
from typing import Optional


def get_env_bool(key: str, default: bool = True) -> bool:
    """读取布尔类型的环境变量"""
    value = os.getenv(key, str(default).lower())
    return value.lower() == 'true'


def get_env_str(key: str, default: str = "") -> str:
    """读取字符串类型的环境变量，自动去除首尾空格"""
    return os.getenv(key, default).strip()


def get_env_int(key: str, default: int) -> int:
    """读取整数类型的环境变量"""
    try:
        return int(os.getenv(key, str(default)).strip())
    except (ValueError, TypeError):
        return default


class DatabaseConfig:
    """数据库配置类 - 统一管理数据库相关环境变量"""
    
    @staticmethod
    def is_embedded_mode() -> bool:
        """是否使用嵌入式 PostgreSQL"""
        return get_env_bool('USE_EMBEDDED_PG', True)
    
    @staticmethod
    def get_host() -> str:
        """获取数据库主机地址"""
        return get_env_str('DATABASE_HOST', 'localhost')
    
    @staticmethod
    def get_port() -> int:
        """获取数据库端口"""
        # 嵌入式模式默认 15432，外部模式默认 5432
        default_port = 15432 if DatabaseConfig.is_embedded_mode() else 5432
        return get_env_int('DATABASE_PORT', default_port)
    
    @staticmethod
    def get_user() -> str:
        """获取数据库用户名"""
        return get_env_str('DATABASE_USER', 'postgres')
    
    @staticmethod
    def get_password() -> str:
        """获取数据库密码"""
        return get_env_str('DATABASE_PASSWORD', '')
    
    @staticmethod
    def get_database() -> str:
        """获取数据库名称"""
        return get_env_str('DATABASE_NAME', 'knowledge_base')
    
    @staticmethod
    def get_connection_url() -> str:
        """构建数据库连接 URL"""
        return (
            f"postgresql+asyncpg://"
            f"{DatabaseConfig.get_user()}:{DatabaseConfig.get_password()}"
            f"@{DatabaseConfig.get_host()}:{DatabaseConfig.get_port()}"
            f"/{DatabaseConfig.get_database()}"
        )
    
    @staticmethod
    def get_config_dict() -> dict:
        """获取数据库配置配置字典"""
        return {
            'host': DatabaseConfig.get_host(),
            'port': DatabaseConfig.get_port(),
            'user': DatabaseConfig.get_user(),
            'password': DatabaseConfig.get_password(),
            'database': DatabaseConfig.get_database(),
        }
