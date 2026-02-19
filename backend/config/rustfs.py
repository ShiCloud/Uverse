"""
RustFS 配置文件
"""
import os
import platform
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 从环境变量读取 store 目录，默认为相对路径
store_dir_env = os.getenv("STORE_DIR", "store")
if os.path.isabs(store_dir_env):
    STORE_DIR = Path(store_dir_env)
else:
    # 相对路径，基于 backend 目录
    STORE_DIR = PROJECT_ROOT / store_dir_env

# 根据平台确定可执行文件名
_is_windows = platform.system() == "Windows"
RUSTFS_BINARY_NAME = "rustfs.exe" if _is_windows else "rustfs"

# RustFS 配置
RUSTFS_CONFIG = {
    # 执行文件路径
    "binary_path": str(STORE_DIR / RUSTFS_BINARY_NAME),
    
    # 数据存储目录
    "data_dir": str(STORE_DIR / "data"),
    
    # 服务配置
    "address": os.getenv("RUSTFS_ADDRESS", ":9000"),
    "access_key": os.getenv("RUSTFS_ACCESS_KEY", "rustfsadmin"),
    "secret_key": os.getenv("RUSTFS_SECRET_KEY", "rustfsadmin"),
    "region": os.getenv("RUSTFS_REGION", "us-east-1"),
    
    # 控制台配置
    "console_enable": os.getenv("RUSTFS_CONSOLE_ENABLE", "false").lower() == "true",
    "console_address": os.getenv("RUSTFS_CONSOLE_ADDRESS", ":9001"),
    
    # 存储桶配置
    "default_bucket": "uverse-storage",
    "buckets": {
        "uploads": "原始上传文件",
        "markdowns": "转换后的Markdown文件",
        "images": "图片资源",
    }
}

# S3 客户端配置
def get_s3_config():
    """获取 S3 客户端配置"""
    return {
        "endpoint_url": f"http://127.0.0.1{RUSTFS_CONFIG['address']}",
        "aws_access_key_id": RUSTFS_CONFIG["access_key"],
        "aws_secret_access_key": RUSTFS_CONFIG["secret_key"],
        "region_name": RUSTFS_CONFIG["region"],
    }
