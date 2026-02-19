"""
数据库工具模块 - 统一处理数据库连接和测试
"""
import asyncio
from typing import Optional, Tuple


async def test_connection(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    timeout: int = 5,
    verbose: bool = True
) -> Tuple[bool, str]:
    """
    测试数据库连接
    
    Args:
        host: 数据库主机地址
        port: 数据库端口
        user: 用户名
        password: 密码
        database: 数据库名称
        timeout: 连接超时时间（秒）
        verbose: 是否打印日志
        
    Returns:
        Tuple[bool, str]: (是否成功, 消息)
    """
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            timeout=timeout
        )
        version = await conn.fetchval("SELECT version()")
        await conn.close()
        
        if verbose:
            print(f"[OK] 数据库连接成功: {version[:50]}...")
        return True, f"连接成功: {version[:50]}..."
    except Exception as e:
        error_msg = str(e)
        if verbose:
            print(f"[ERROR] 数据库连接失败: {error_msg}")
        return False, f"连接失败: {error_msg}"


async def test_connection_with_retry(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    max_retries: int = 3,
    retry_delay: int = 2,
    timeout: int = 5,
    verbose: bool = True
) -> Tuple[bool, str]:
    """
    测试数据库连接（带重试）
    
    Args:
        host: 数据库主机地址
        port: 数据库端口
        user: 用户名
        password: 密码
        database: 数据库名称
        max_retries: 最大重试次数
        retry_delay: 重试间隔（秒）
        timeout: 连接超时时间（秒）
        verbose: 是否打印日志
        
    Returns:
        Tuple[bool, str]: (是否成功, 消息)
    """
    for attempt in range(1, max_retries + 1):
        success, message = await test_connection(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            timeout=timeout,
            verbose=verbose
        )
        
        if success:
            return True, message
        
        if attempt < max_retries:
            if verbose:
                print(f"[WAIT] 连接尝试 {attempt}/{max_retries} 失败，{retry_delay}秒后重试...")
            await asyncio.sleep(retry_delay)
    
    return False, f"连接失败（已重试{max_retries}次）"


def print_db_config(
    host: str,
    port: int,
    user: str,
    database: str,
    prefix: str = ""
):
    """打印数据库配置信息（隐藏密码）"""
    print(f"{prefix}主机地址: {host}")
    print(f"{prefix}端口: {port}")
    print(f"{prefix}用户名: {user}")
    print(f"{prefix}数据库: {database}")
