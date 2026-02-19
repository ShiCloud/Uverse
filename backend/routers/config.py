"""
配置管理路由
用于读取和更新 .env 配置文件
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# 导入公共工具模块
from utils import DatabaseConfig, test_connection, resolve_path
from utils import check_executable, check_subdir
from utils.path import get_user_data_dir

router = APIRouter()


# 配置文件路径 - 支持开发和 PyInstaller 打包环境
def get_env_file_path() -> Path:
    """获取 .env 文件路径 - 适配开发和打包环境"""
    import sys
    
    # 用户可写目录
    user_data_dir = get_user_data_dir()
    user_env_path = user_data_dir / ".env"
    
    # PyInstaller 打包环境
    if getattr(sys, 'frozen', False):
        # 在 PyInstaller 中，__file__ 指向 _internal/ 目录
        # 需要使用 sys.executable 来获取正确的目录
        exe_dir = Path(sys.executable).parent
        bundled_path = exe_dir / ".env"
        
        # 如果用户目录没有 .env，从应用包复制一份
        if not user_env_path.exists() and bundled_path.exists():
            user_data_dir.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(bundled_path, user_env_path)
        
        # 使用用户目录的配置文件（可写）
        if user_env_path.exists():
            return user_env_path
        
        # 如果复制失败，返回用户目录路径（即使不存在，让调用方处理）
        return user_env_path
    
    # 开发环境：使用当前文件所在目录的父目录（backend/）
    dev_path = Path(__file__).parent.parent / ".env"
    
    # 优先使用项目目录的配置文件
    if dev_path.exists():
        return dev_path
    
    # 如果项目目录没有，使用用户目录（兼容旧版本）
    if user_env_path.exists():
        return user_env_path
    
    # 默认返回项目目录路径（即使不存在，让调用方处理）
    return dev_path

ENV_FILE_PATH = get_env_file_path()


class ConfigItem(BaseModel):
    """配置项模型"""
    key: str
    value: str
    description: Optional[str] = None
    category: str = "general"


class ConfigUpdateRequest(BaseModel):
    """配置更新请求模型"""
    configs: Dict[str, str]


class ConfigResponse(BaseModel):
    """配置响应模型"""
    success: bool
    message: str
    configs: Optional[List[ConfigItem]] = None


# 配置项分类和描述 - 只保留数据库、服务、路径、MinerU四类配置
CONFIG_METADATA: Dict[str, Dict[str, Any]] = {
    # 应用版本配置
    "APP_VERSION": {"category": "server", "description": "应用版本号"},
    
    # 服务端口配置
    "PORT": {"category": "server", "description": "后端服务端口"},
    
    # 服务路径配置
    "POSTGRES_DIR": {"category": "server", "description": "PostgreSQL 目录 (需包含 bin/psql)"},
    "STORE_DIR": {"category": "server", "description": "存储目录 (需包含 rustfs 可执行文件)"},
    "MODELS_DIR": {"category": "server", "description": "模型目录 (需包含 OpenDataLab/ 子目录)"},
    "TEMP_DIR": {"category": "server", "description": "临时文件目录"},
    
    # 数据库配置（嵌入式和外部模式共用）
    "USE_EMBEDDED_PG": {"category": "database", "description": "使用嵌入式 PostgreSQL（false则连接外部数据库）"},
    "DATABASE_HOST": {"category": "database", "description": "数据库主机地址（嵌入式默认localhost）"},
    "DATABASE_PORT": {"category": "database", "description": "数据库端口（嵌入式默认15432）"},
    "DATABASE_USER": {"category": "database", "description": "数据库用户名"},
    "DATABASE_PASSWORD": {"category": "database", "description": "数据库密码"},
    "DATABASE_NAME": {"category": "database", "description": "数据库名称"},
    
    # PDF解析配置
    "MINERU_BACKEND": {"category": "mineru", "description": "PDF解析后端"},
    "MINERU_DEVICE": {"category": "mineru", "description": "设备模式"},
    "MINERU_VRAM": {"category": "mineru", "description": "GPU显存限制 (MB)"},
    "MINERU_VIRTUAL_VRAM_SIZE": {"category": "mineru", "description": "虚拟显存大小 (GB)"},
    "MINERU_OUTPUT_DIR": {"category": "mineru", "description": "PDF解析输出目录"},
}


def parse_env_file() -> List[ConfigItem]:
    """解析 .env 文件，提取配置项和注释"""
    configs = []
    current_description = []
    current_category = "general"
    
    if not ENV_FILE_PATH.exists():
        return configs
    
    with open(ENV_FILE_PATH, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for line in lines:
        line = line.rstrip()
        
        # 空行 - 重置描述
        if not line.strip():
            current_description = []
            continue
        
        # 注释行
        if line.strip().startswith('#'):
            comment_text = line.strip()[1:].strip()
            # 检查是否是分类标题
            if '配置' in comment_text or '设置' in comment_text:
                # 提取分类
                if '数据库' in comment_text:
                    current_category = "database"
                elif '服务' in comment_text:
                    current_category = "server"
                elif 'MinerU' in comment_text or 'PDF' in comment_text:
                    current_category = "mineru"
                elif 'OpenAI' in comment_text:
                    current_category = "openai"
                elif '日志' in comment_text:
                    current_category = "logging"
                continue
            current_description.append(comment_text)
            continue
        
        # 配置项行
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', line)
        if match:
            key = match.group(1)
            value = match.group(2).strip()
            
            # 移除行尾注释
            if '#' in value and not value.startswith('"') and not value.startswith("'"):
                value = value.split('#')[0].strip()
            
            # 获取元数据 - 只处理在 CONFIG_METADATA 中定义的配置项
            metadata = CONFIG_METADATA.get(key)
            if metadata is None:
                # 不在白名单中的配置项，跳过
                current_description = []
                continue
            
            category = metadata.get("category", "general")
            description = metadata.get("description")
            
            # 如果没有元数据描述，使用注释
            if not description and current_description:
                description = ' '.join(current_description)
            
            configs.append(ConfigItem(
                key=key,
                value=value,
                description=description,
                category=category
            ))
            current_description = []
    
    # 为隐藏配置项提供默认值
    # 检查 TEMP_DIR 是否存在，如果不存在则添加默认值
    temp_dir_exists = any(c.key == 'TEMP_DIR' for c in configs)
    if not temp_dir_exists:
        temp_metadata = CONFIG_METADATA.get('TEMP_DIR', {})
        default_temp_dir = str(get_user_data_dir() / 'temp')
        configs.append(ConfigItem(
            key='TEMP_DIR',
            value=default_temp_dir,
            description=temp_metadata.get('description', '临时文件目录'),
            category=temp_metadata.get('category', 'server')
        ))
    
    return configs


def update_env_file(updates: Dict[str, str]) -> bool:
    """更新 .env 文件中的配置项"""
    if not ENV_FILE_PATH.exists():
        raise HTTPException(status_code=404, detail="配置文件不存在")
    
    with open(ENV_FILE_PATH, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    updated_keys = set()
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # 检查是否是配置项行
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', stripped)
        if match:
            key = match.group(1)
            if key in updates:
                # 保留原有的格式（包括前导空格和注释）
                leading_space = line[:len(line) - len(line.lstrip())]
                # 检查是否有行尾注释
                comment_match = re.search(r'\s+#.*$', line)
                comment = comment_match.group(0) if comment_match else ''
                
                new_value = updates[key]
                # 如果值包含特殊字符，需要引号
                if ' ' in new_value or '#' in new_value:
                    if not (new_value.startswith('"') and new_value.endswith('"')):
                        new_value = f'"{new_value}"'
                
                new_line = f"{leading_space}{key}={new_value}{comment}\n"
                new_lines.append(new_line)
                updated_keys.add(key)
                continue
        
        new_lines.append(line)
    
    # 如果有未找到的配置项，添加到文件末尾
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"\n{key}={value}\n")
    
    with open(ENV_FILE_PATH, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    return True


@router.get("/config", response_model=ConfigResponse)
async def get_configs():
    """获取所有配置项"""
    try:
        configs = parse_env_file()
        return ConfigResponse(
            success=True,
            message="获取配置成功",
            configs=configs
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取配置失败: {str(e)}")


@router.post("/config", response_model=ConfigResponse)
async def update_configs(request: ConfigUpdateRequest):
    """更新配置项"""
    try:
        update_env_file(request.configs)
        return ConfigResponse(
            success=True,
            message="配置更新成功，重启服务后生效",
            configs=None
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")


@router.get("/config/categories")
async def get_config_categories():
    """获取配置分类列表 - 返回数据库、服务、MinerU三类"""
    categories = {
        "server": "服务配置",
        "database": "数据库配置",
        "mineru": "PDF解析配置",
    }
    return {"categories": categories}


class PathCheckRequest(BaseModel):
    """路径检查请求模型"""
    paths: Dict[str, str]


class PathCheckResponse(BaseModel):
    """路径检查响应模型"""
    valid: bool
    results: Dict[str, bool]
    errors: Dict[str, str]


@router.post("/config/check-paths", response_model=PathCheckResponse)
async def check_paths(request: PathCheckRequest):
    """检查路径是否存在，并验证关键文件/目录"""
    results = {}
    errors = {}
    all_valid = True
    
    backend_dir = Path(__file__).parent.parent
    is_windows = os.name == 'nt'
    is_embedded = DatabaseConfig.is_embedded_mode()
    
    # 定义各路径需要检查的具体内容
    CHECK_TARGETS = {
        'POSTGRES_DIR': ('bin/psql', 'PostgreSQL 客户端 (bin/psql)'),
        'STORE_DIR': ('rustfs', 'RustFS 可执行文件 (rustfs)'),
        'MODELS_DIR': (None, 'OpenDataLab'),  # (子目录名, 描述)
        'TEMP_DIR': None,
    }
    
    for key, path_str in request.paths.items():
        # 外部数据库模式下跳过 POSTGRES_DIR 检查
        if key == 'POSTGRES_DIR' and not is_embedded:
            continue
        
        # 解析路径
        base_path = resolve_path(path_str, backend_dir)
        if not base_path:
            results[key] = False
            all_valid = False
            errors[key] = f"路径未配置"
            continue
        
        target = CHECK_TARGETS.get(key)
        
        if target is None:
            # 只需要检查目录本身
            exists = base_path.exists()
            results[key] = exists
            if not exists:
                all_valid = False
                errors[key] = f"目录不存在: {base_path}"
        elif key == 'POSTGRES_DIR' or key == 'STORE_DIR':
            # 检查可执行文件
            exe_name = target[0]
            exists = check_executable(base_path, exe_name, is_windows)
            results[key] = exists
            if not exists:
                errors[key] = f"未找到 {target[1]}: {base_path / exe_name}"
                all_valid = False
        elif key == 'MODELS_DIR':
            # 检查子目录
            subdir = target[1]
            exists = check_subdir(base_path, subdir)
            results[key] = exists
            if not exists:
                errors[key] = f"未找到 {target[1]}: {base_path / subdir}"
                all_valid = False
    
    return PathCheckResponse(
        valid=all_valid,
        results=results,
        errors=errors
    )


class DBStatusResponse(BaseModel):
    """数据库状态检查响应模型"""
    available: bool
    mode: str  # 'embedded' 或 'external'
    error: Optional[str] = None


@router.get("/config/db-status", response_model=DBStatusResponse)
async def check_db_status():
    """检查数据库连接状态"""
    use_embedded_pg = os.getenv("USE_EMBEDDED_PG", "true").lower() == "true"
    
    # 导入 main 模块获取全局状态
    import sys
    main_module = sys.modules.get('__main__')
    
    print(f"[DB Status API] use_embedded_pg={use_embedded_pg}, main_module={main_module}")
    
    if use_embedded_pg:
        # 嵌入式模式：检查 POSTGRES_AVAILABLE 标志
        postgres_available = getattr(main_module, '_postgres_available', False)
        print(f"[DB Status API] 嵌入式模式: _postgres_available={postgres_available}")
        return DBStatusResponse(
            available=postgres_available,
            mode='embedded',
            error=None if postgres_available else '嵌入式 PostgreSQL 未启动'
        )
    else:
        # 外部模式：检查 POSTGRES_AVAILABLE 标志
        postgres_available = getattr(main_module, '_postgres_available', False)
        print(f"[DB Status API] 外部模式: _postgres_available={postgres_available}")
        if postgres_available:
            return DBStatusResponse(
                available=True,
                mode='external',
                error=None
            )
        else:
            # 获取配置信息用于错误提示
            db_host = os.getenv("DATABASE_HOST", "").strip()
            print(f"[DB Status API] 外部模式不可用: host={db_host}")
            if not db_host:
                return DBStatusResponse(
                    available=False,
                    mode='external',
                    error='未配置外部数据库地址 (DATABASE_HOST)'
                )
            else:
                return DBStatusResponse(
                    available=False,
                    mode='external',
                    error=f'无法连接到外部数据库: {db_host}'
                )


class DBConnectionTestRequest(BaseModel):
    """数据库连接测试请求模型"""
    host: str
    port: str = "5432"
    user: str = "postgres"
    password: str = ""
    database: str = "knowledge_base"


class DBConnectionTestResponse(BaseModel):
    """数据库连接测试响应模型"""
    success: bool
    message: str


@router.post("/config/test-db-connection", response_model=DBConnectionTestResponse)
async def test_db_connection(request: DBConnectionTestRequest):
    """
    测试外部数据库连接。
    
    用于保存配置前验证数据库连接是否可用。
    """
    print(f"[DB Test] 测试连接: host={request.host}, port={request.port}, user={request.user}, database={request.database}")
    
    success, message = await test_connection(
        host=request.host,
        port=int(request.port),
        user=request.user,
        password=request.password,
        database=request.database,
        timeout=5,
        verbose=False  # 我们自己打印日志
    )
    
    print(f"[DB Test] 结果: {message}")
    return DBConnectionTestResponse(success=success, message=message)


@router.post("/shutdown")
async def shutdown():
    """关闭应用程序"""
    import threading
    import time
    
    def delayed_shutdown():
        """延迟关闭，给响应时间"""
        time.sleep(1)
        os._exit(0)
    
    # 启动后台线程执行关闭
    threading.Thread(target=delayed_shutdown, daemon=True).start()
    
    return {"success": True, "message": "应用程序正在关闭..."}
