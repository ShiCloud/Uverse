"""
后端主入口 - Python + Langchain + FastAPI
支持嵌入式 PostgreSQL 模式
"""
import asyncio
import os
import sys
import time
from pathlib import Path

# 导入公共工具模块
from utils import DatabaseConfig, test_connection_with_retry, print_db_config
from utils import resolve_path, check_executable, check_subdir, get_default_dir


# 向后兼容的别名
get_user_data_dir = lambda: get_default_dir('')


def check_port_available(host: str, port: int) -> bool:
    """检查端口是否可用"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result != 0  # 0 表示端口被占用
    except:
        return False


def kill_process_on_port(port: int):
    """尝试杀死占用指定端口的进程"""
    import subprocess
    import platform
    
    system = platform.system()
    try:
        if system == "Darwin" or system == "Linux":
            # 使用 lsof 查找占用端口的进程
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid:
                        print(f"🔪 杀死占用端口 {port} 的进程: {pid}")
                        subprocess.run(["kill", "-9", pid], capture_output=True)
        elif system == "Windows":
            # 使用 netstat 查找占用端口的进程
            result = subprocess.run(
                ["netstat", "-ano", "|", "findstr", f":{port}"],
                capture_output=True,
                text=True,
                shell=True
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        print(f"🔪 杀死占用端口 {port} 的进程: {pid}")
                        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
    except Exception as e:
        print(f"⚠️ 尝试杀死端口 {port} 的进程时出错: {e}")

# 获取 .env 文件路径 - 适配开发和打包环境
def get_env_file_path() -> Path:
    """获取 .env 文件路径"""
    user_data_dir = get_user_data_dir()
    user_env_path = user_data_dir / ".env"
    
    # PyInstaller 打包环境
    if getattr(sys, 'frozen', False):
        # 在 PyInstaller 中，__file__ 指向 _internal/ 目录
        # 需要使用 sys.executable 来获取 uverse-backend/ 目录
        exe_dir = Path(sys.executable).parent
        bundled_path = exe_dir / ".env"
        
        # 如果用户目录没有 .env，从应用包复制一份
        if not user_env_path.exists() and bundled_path.exists():
            user_data_dir.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(bundled_path, user_env_path)
        
        # 使用用户目录的配置文件（可写）
        return user_env_path if user_env_path.exists() else bundled_path
    
    # 开发环境：使用项目目录的配置文件
    dev_path = Path(__file__).parent / ".env"
    if dev_path.exists():
        return dev_path
    
    # 如果项目目录没有，使用用户目录
    return user_env_path if user_env_path.exists() else dev_path

# 加载 .env 文件
from dotenv import load_dotenv
env_path = get_env_file_path()
if env_path.exists():
    load_dotenv(env_path)

# 设置默认目录（如果未配置）- 使用用户可写目录
def get_default_user_dir(subdir: str) -> Path:
    """获取默认用户目录路径 - 与日志目录同级"""
    if os.name == 'nt':  # Windows
        base_dir = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif os.uname().sysname == 'Darwin':  # macOS
        base_dir = Path.home() / 'Library' / 'Application Support'
    else:  # Linux
        base_dir = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return base_dir / 'Uverse' / subdir

# 如果 TEMP_DIR 未设置，使用默认值
if not os.getenv('TEMP_DIR'):
    default_temp = get_default_user_dir('temp')
    os.environ['TEMP_DIR'] = str(default_temp)
    default_temp.mkdir(parents=True, exist_ok=True)

# 如果 MINERU_OUTPUT_DIR 未设置，使用默认值
if not os.getenv('MINERU_OUTPUT_DIR'):
    default_output = get_default_user_dir('outputs')
    os.environ['MINERU_OUTPUT_DIR'] = str(default_output)
    default_output.mkdir(parents=True, exist_ok=True)

# 初始化文件日志管理器（在导入其他模块之前）
from core.file_logger import get_file_log_manager
file_log_manager = get_file_log_manager()

# 设置 logging 处理器，将日志写入文件
import logging

class FileLogHandler(logging.Handler):
    """将日志写入文件的处理器 - 只记录应用日志，过滤第三方库日志"""
    
    # 只记录这些来源的日志（应用自己的日志）
    # 为空列表时表示记录所有非黑名单的日志
    APP_SOURCES = []
    
    # 黑名单：这些来源的日志不记录（第三方库的日志）
    BLACKLIST_SOURCES = [
        'uvicorn', 'uvicorn.error', 'uvicorn.access', 'uvicorn.protocols',
        'fastapi', 'starlette', 'websockets', 'asyncio',
        'sqlalchemy', 'sqlalchemy.engine', 'sqlalchemy.pool',
        'botocore', 'boto3', 'urllib3', 'requests',
        'httpcore', 'httpx', 'aiosqlite',
        'PIL', 'matplotlib', 'numpy'
    ]
    
    # 需要过滤的消息模式
    SKIP_MESSAGES = [
        'TEXT', 'BYTES', 'ping', 'pong',  # WebSocket 帧
        'Application startup complete', 'Started server process',
        'Waiting for application', 'Application shutdown complete',
        'connection open', 'connection closed',
        '> ', '< ',  # HTTP 请求/响应详情
        'GET /', 'POST /', 'PUT /', 'DELETE /', 'OPTIONS /',  # 访问日志（uvicorn.access 已经处理）
    ]
    
    def emit(self, record):
        try:
            # 检查来源是否在黑名单中
            for blacklisted in self.BLACKLIST_SOURCES:
                if record.name.startswith(blacklisted):
                    # 即使是黑名单，ERROR 级别以上的错误还是要记录
                    if record.levelno < logging.ERROR:
                        return
            
            # 检查消息是否需要跳过
            msg = record.getMessage()
            for skip_pattern in self.SKIP_MESSAGES:
                if skip_pattern in msg:
                    return
            
            # 过滤 WebSocket 帧内容
            if len(msg) > 500 and ('{"type"' in msg or 'ping' in msg.lower()):
                return
            
            # 记录日志
            file_log_manager.add_log(
                level=record.levelname,
                message=msg,
                source=record.name
            )
        except Exception:
            self.handleError(record)

# 添加处理器到 root logger（确保只添加一次）
root_logger = logging.getLogger()
# 检查是否已添加 FileLogHandler，避免 uvicorn 重载时重复添加
file_handler = None
for h in root_logger.handlers:
    if isinstance(h, FileLogHandler):
        file_handler = h
        break

if file_handler is None:
    file_handler = FileLogHandler()
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

# 设置 root logger 为 INFO 级别（至少记录 INFO 级别的日志）
# 具体的过滤在 FileLogHandler 中处理
root_logger.setLevel(logging.INFO)

# 为应用自己的模块设置 DEBUG 级别
app_loggers = ['routers', 'services', 'core', 'models', '__main__']
for logger_name in app_loggers:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    # 确保处理器被添加（但不要重复添加，也不要给已经继承 root 处理器的 logger 添加）
    if not logger.handlers and logger.parent != root_logger:
        logger.addHandler(file_handler)

# 重定向 print 到 logging（用于捕获启动时的 print 输出）
import sys

# 先保存原始 stdout（用于调试输出）
_original_stdout = sys.stdout
_original_stderr = sys.stderr

# 使用 sys.modules 存储全局去重集合，确保在模块重载时也能保持
# 当 main.py 被作为 __main__ 和 main 两次导入时，这个集合会被共享
# 检查 __main__ 模块中是否已经有去重集合
_main_module = sys.modules.get('__main__')

if _main_module and hasattr(_main_module, '_print_log_seen_messages') and _main_module._print_log_seen_messages is not None:
    _print_log_seen_messages = _main_module._print_log_seen_messages
else:
    _print_log_seen_messages = set()
    # 在 __main__ 模块中存储，以便后续导入的 main 模块可以访问
    if _main_module:
        _main_module._print_log_seen_messages = _print_log_seen_messages

class PrintToLog:
    """将 print 输出重定向到日志"""
    
    def __init__(self, logger_name='__main__'):
        self.logger = logging.getLogger(logger_name)
        self._buffer = ''
        # 使用全局变量
        self._seen = _print_log_seen_messages
    
    def write(self, message):
        # 累积到缓冲区，直到遇到换行符
        self._buffer += message
        
        # 处理完整的行
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            line = line.rstrip()
            if line:
                self._emit_line(line)
    
    def _emit_line(self, line):
        # 使用行内容作为去重键（简单去重，同一行的多次输出只记录一次）
        if line in self._seen:
            return
        self._seen.add(line)
        
        # 限制缓存大小，防止内存泄漏
        if len(self._seen) > 1000:
            self._seen.clear()
        
        # 根据内容判断级别
        level = logging.INFO
        if '❌' in line or '错误' in line or 'Error' in line:
            level = logging.ERROR
        elif '⚠️' in line or '警告' in line or 'Warning' in line:
            level = logging.WARNING
        
        self.logger.log(level, line)
    
    def flush(self):
        # 刷新缓冲区中剩余的内容
        if self._buffer.strip():
            self._emit_line(self._buffer)
            self._buffer = ''

# 立即启用 print 重定向（必须在任何 print 语句之前）
# 注意：这会在 __main__ 块中再次设置，但去重机制会避免重复日志
_print_redirector = PrintToLog('__main__')
sys.stdout = _print_redirector
sys.stderr = _print_redirector

def check_required_files():
    """
    检查必要的文件/目录是否存在。
    
    注意：此函数只检查文件/目录的存在性，不涉及任何网络连接或数据库连接测试。
    数据库连接测试在 init_database() 异步函数中进行。
    """
    # 防重入检查
    _main = sys.modules.get('__main__')
    if _main and getattr(_main, '_files_checked', False):
        return (
            getattr(_main, '_store_available', False),
            getattr(_main, '_postgres_dir_available', False),
            getattr(_main, '_models_available', False)
        )
    
    backend_dir = Path(__file__).parent
    is_windows = os.name == 'nt'
    is_embedded = DatabaseConfig.is_embedded_mode()
    
    # 解析路径
    store_dir = resolve_path(os.getenv("STORE_DIR", ""), backend_dir)
    postgres_dir = resolve_path(os.getenv("POSTGRES_DIR", ""), backend_dir)
    models_dir = resolve_path(os.getenv("MODELS_DIR", ""), backend_dir)
    
    global STORE_AVAILABLE, MODELS_AVAILABLE
    
    # 检查 RustFS 可执行文件
    if store_dir:
        STORE_AVAILABLE = check_executable(store_dir, 'rustfs', is_windows)
        rustfs_display = str(store_dir / 'rustfs')
    else:
        rustfs_display = "(未配置)"
        STORE_AVAILABLE = False
    
    # 检查 PostgreSQL 目录（仅嵌入式模式）
    if is_embedded and postgres_dir:
        pg_ctl_path = postgres_dir / 'bin' / 'pg_ctl'
        postgres_dir_available = pg_ctl_path.exists()
        pg_display = str(pg_ctl_path)
    elif is_embedded:
        postgres_dir_available = False
        pg_display = "(未配置)"
    else:
        postgres_dir_available = True
        pg_display = "(外部数据库模式，跳过目录检查)"
    
    # 检查 Models 目录
    if models_dir:
        MODELS_AVAILABLE = check_subdir(models_dir, 'OpenDataLab')
        models_display = str(models_dir / 'OpenDataLab')
    else:
        MODELS_AVAILABLE = False
        models_display = "(未配置)"
    
    print("\n🔍 检查必要文件/目录...")
    print(f"  {'✅' if STORE_AVAILABLE else '⚠️'} store/rustfs: {rustfs_display}")
    print(f"  {'✅' if postgres_dir_available else '⚠️'} postgres/bin/pg_ctl: {pg_display}")
    print(f"  {'✅' if MODELS_AVAILABLE else '⚠️'} models/OpenDataLab: {models_display}")
    
    if not STORE_AVAILABLE or not postgres_dir_available or not MODELS_AVAILABLE:
        print("\n⚠️ 警告: 部分关键组件缺失，相关功能将不可用:")
        if not STORE_AVAILABLE:
            print("   - store/rustfs: 文件存储服务不可用")
        if not postgres_dir_available:
            print("   - postgres: PostgreSQL 目录未配置或文件缺失")
        if not MODELS_AVAILABLE:
            print("   - models/OpenDataLab: AI 模型解析功能不可用")
        print("   请通过配置页面设置正确的路径。\n")
    else:
        print("   所有必要文件/目录检查通过\n")
    
    # 存储结果到 __main__ 模块（防重入）
    if _main:
        _main._files_checked = True
        _main._store_available = STORE_AVAILABLE
        _main._postgres_dir_available = postgres_dir_available
        _main._models_available = MODELS_AVAILABLE
    
    return STORE_AVAILABLE, postgres_dir_available, MODELS_AVAILABLE


async def init_database() -> bool:
    """
    初始化数据库连接。
    
    根据配置模式（嵌入式或外部）进行相应的数据库初始化和连接测试。
    此函数执行实际的数据库连接测试，与 check_required_files() 的文件检查分离。
    
    Returns:
        bool: 数据库是否可用
    """
    global POSTGRES_AVAILABLE
    
    use_embedded_pg = os.getenv("USE_EMBEDDED_PG", "true").lower() == "true"
    
    print(f"\n🔧 数据库模式: {'嵌入式 PostgreSQL' if use_embedded_pg else '外部 PostgreSQL'}")
    
    if use_embedded_pg:
        return await _init_embedded_postgres()
    else:
        return await _init_external_postgres()


async def _init_embedded_postgres() -> bool:
    """初始化嵌入式 PostgreSQL 数据库。"""
    global POSTGRES_AVAILABLE
    
    postgres_dir = resolve_path(os.getenv("POSTGRES_DIR", ""), Path(__file__).parent)
    if not postgres_dir:
        print("⚠️ PostgreSQL 目录未配置，嵌入式数据库无法启动")
        POSTGRES_AVAILABLE = False
        return False
    
    pg_ctl_path = postgres_dir / 'bin' / 'pg_ctl'
    if not pg_ctl_path.exists():
        print(f"⚠️ PostgreSQL 可执行文件不存在: {pg_ctl_path}")
        POSTGRES_AVAILABLE = False
        return False
    
    from core.postgres_manager import get_postgres_manager
    pg_manager = get_postgres_manager()
    
    try:
        print("📦 启动嵌入式 PostgreSQL...")
        if pg_manager.start():
            os.environ["DATABASE_URL"] = pg_manager.get_connection_url()
            print(f"🔌 数据库连接: {pg_manager.get_connection_url()}")
            POSTGRES_AVAILABLE = True
            return True
        else:
            print("⚠️ 无法启动嵌入式 PostgreSQL")
            POSTGRES_AVAILABLE = False
            return False
    except Exception as e:
        print(f"⚠️ PostgreSQL 启动失败: {e}")
        POSTGRES_AVAILABLE = False
        return False


async def _init_external_postgres() -> bool:
    """
    初始化外部 PostgreSQL 数据库连接。
    连接失败时会重试3次，最后失败不会退出进程。
    """
    global POSTGRES_AVAILABLE
    
    config = DatabaseConfig.get_config_dict()
    
    if not config['host']:
        print("⚠️ 未配置 DATABASE_HOST，外部数据库无法连接")
        print("   请前往设置页面配置外部数据库连接信息")
        POSTGRES_AVAILABLE = False
        return False
    
    # 设置 DATABASE_URL
    os.environ["DATABASE_URL"] = DatabaseConfig.get_connection_url()
    print(f"🔗 配置外部 PostgreSQL: {config['host']}:{config['port']}/{config['database']}")
    
    # 测试连接（重试3次）
    success, message = await test_connection_with_retry(
        **config,
        max_retries=3,
        retry_delay=2,
        timeout=5,
        verbose=True
    )
    
    if success:
        POSTGRES_AVAILABLE = True
        return True
    
    # 失败时打印配置信息
    print("   请检查数据库配置：")
    print_db_config(**config, prefix="   - ")
    print("\n⚠️ 外部数据库连接失败，数据库功能不可用")
    print("   请前往设置页面配置正确的数据库连接信息\n")
    POSTGRES_AVAILABLE = False
    return False


# 全局标志位：各服务是否可用（在 lifespan 中初始化）
STORE_AVAILABLE = False
POSTGRES_AVAILABLE = False
MODELS_AVAILABLE = False


# 使用 sys.modules 存储跨模块实例的全局状态（防止 uvicorn 重载导致重复执行）
import sys
_main_module = sys.modules.get('__main__')
if _main_module and not hasattr(_main_module, '_uvicorn_startup_done'):
    _main_module._uvicorn_startup_done = False
    _main_module._uvicorn_shutdown_done = False


def is_startup_done() -> bool:
    """检查启动逻辑是否已执行"""
    _main = sys.modules.get('__main__')
    return getattr(_main, '_uvicorn_startup_done', False) if _main else False


def mark_startup_done():
    """标记启动逻辑已执行"""
    _main = sys.modules.get('__main__')
    if _main:
        _main._uvicorn_startup_done = True


def is_shutdown_done() -> bool:
    """检查关闭逻辑是否已执行"""
    _main = sys.modules.get('__main__')
    return getattr(_main, '_uvicorn_shutdown_done', False) if _main else False


def mark_shutdown_done():
    """标记关闭逻辑已执行"""
    _main = sys.modules.get('__main__')
    if _main:
        _main._uvicorn_shutdown_done = True


# 先设置环境变量，再导入其他模块
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# 导入路由
from routers import chat, documents, health, config, logs

# 延迟导入其他模块（在 lifespan 中导入）
# from core.postgres_manager import get_postgres_manager  # 移到 lifespan 中




@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 - 所有启动逻辑都在这里执行，避免模块级别重复执行"""
    import asyncio
    
    # 获取主模块引用（用于存储全局状态）
    _main = sys.modules.get('__main__')
    
    # 设置事件循环到日志管理器
    loop = asyncio.get_event_loop()
    file_log_manager.set_event_loop(loop)
    
    # 启动时执行（带防重入检查）
    if is_startup_done():
        print("🚀 后端服务启动中... (跳过重复执行)")
        yield
        return
    mark_startup_done()
    
    # ====== 所有启动逻辑从这里开始 ======
    
    # 1. 检查必要文件/目录（仅检查存在性，不涉及网络连接）
    global STORE_AVAILABLE, POSTGRES_AVAILABLE, MODELS_AVAILABLE
    STORE_AVAILABLE, postgres_dir_available, MODELS_AVAILABLE = check_required_files()
    
    # 2. 初始化数据库连接（异步操作，包含实际的连接测试）
    # 注意：数据库初始化独立于文件检查，支持外部数据库模式
    POSTGRES_AVAILABLE = await init_database()
    
    print("🚀 后端服务启动中...")
    
    # 3. 导入并初始化数据库
    # 注意：必须先导入并初始化引擎，再导入模型
    from core.database import init_engine, init_db
    init_engine()  # 根据环境变量 DATABASE_URL 初始化引擎
    
    # 导入模型以确保表被创建
    from core.storage import StorageRecord  # noqa: F401
    
    # 4. 等待数据库就绪并重试（最多3次）
    db_ready = False
    if POSTGRES_AVAILABLE:
        print(f"[DEBUG] POSTGRES_AVAILABLE={POSTGRES_AVAILABLE}，开始初始化数据库...")
        for attempt in range(3):
            try:
                print(f"[DEBUG] 数据库初始化尝试 {attempt + 1}/3...")
                await init_db()
                print("✅ 数据库初始化完成")
                db_ready = True
                break
            except Exception as e:
                print(f"⏳ 数据库初始化尝试 {attempt + 1}/3 失败: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(1)
        
        if not db_ready:
            print("⚠️ 数据库初始化失败，部分功能可能不可用")
            POSTGRES_AVAILABLE = False
    else:
        print("⚠️ PostgreSQL 组件缺失，跳过数据库初始化")
    
    # 更新全局状态（供 API 查询）
    if _main:
        _main._postgres_available = POSTGRES_AVAILABLE
        _main._store_available = STORE_AVAILABLE
    
    # 5. 启动 RustFS 服务
    if STORE_AVAILABLE:
        from services.rustfs_storage import start_rustfs_server
        try:
            rustfs_started = start_rustfs_server()
            if rustfs_started:
                print("✅ RustFS 存储服务已启动")
            else:
                print("⚠️ RustFS 存储服务启动失败，文件存储功能不可用")
                STORE_AVAILABLE = False
        except Exception as e:
            print(f"⚠️ RustFS 存储服务启动失败: {e}，文件存储功能不可用")
            STORE_AVAILABLE = False
    else:
        print("⚠️ RustFS 组件缺失，跳过存储服务启动，文件存储功能不可用")
    
    # 6. 预加载 MinerU（在后台线程中，避免第一次解析请求超时）
    if MODELS_AVAILABLE:
        import threading
        def preload_mineru():
            try:
                print("⏳ 正在预加载 MinerU 模块（后台）...")
                from services.pdf_parser import get_pdf_parser
                # 只是导入模块，不实际解析
                print("✅ MinerU 模块预加载完成")
            except Exception as e:
                print(f"⚠️ MinerU 预加载失败: {e}")
        
        # 在后台线程中预加载，不阻塞启动
        threading.Thread(target=preload_mineru, daemon=True).start()
    
    yield
    
    # 关闭时执行（带防重入检查）
    if is_shutdown_done():
        return  # 防止重复执行
    mark_shutdown_done()
    
    print("👋 后端服务正在关闭...")
    
    # 等待活跃的解析任务完成
    try:
        from routers.documents import _active_tasks
        if _active_tasks:
            print(f"⏳ 等待 {_active_tasks} 个活跃解析任务完成...")
            import asyncio
            # 等待最多 30 秒让任务完成
            for _ in range(30):
                if not _active_tasks:
                    break
                await asyncio.sleep(1)
            if _active_tasks:
                print(f"⚠️ 仍有 {_active_tasks} 个任务未完成，强制关闭")
    except Exception as e:
        print(f"⚠️ 等待任务完成时出错: {e}")
    
    # 关闭进程池
    try:
        from workers.pool import shutdown_process_pool
        shutdown_process_pool()
        print("✅ PDF 解析进程池已关闭")
    except Exception as e:
        print(f"⚠️ 进程池关闭警告: {e}")
    
    # 停止 RustFS 服务
    from services.rustfs_storage import stop_rustfs_server
    try:
        stop_rustfs_server()
        print("✅ RustFS 存储服务已停止")
    except Exception as e:
        print(f"⚠️ RustFS 停止警告: {e}")
    
    # 停止嵌入式 PostgreSQL（仅在使用嵌入式模式时）
    USE_EMBEDDED_PG = os.getenv("USE_EMBEDDED_PG", "true").lower() == "true"
    if USE_EMBEDDED_PG:
        try:
            from core.postgres_manager import get_postgres_manager
            pg_manager = get_postgres_manager()
            pg_manager.stop()
            print("✅ PostgreSQL 已停止")
        except Exception as e:
            print(f"⚠️ PostgreSQL 停止警告: {e}")
    
    print("👋 后端服务已关闭")


app = FastAPI(
    title="知识库 API",
    description="知识库后端服务",
    version="0.1.0",
    lifespan=lifespan
)

# CORS 配置 - 允许 Electron 应用访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（本地应用）
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(health.router, prefix="/api", tags=["健康检查"])
app.include_router(chat.router, prefix="/api/chat", tags=["对话"])
app.include_router(documents.router, prefix="/api/documents", tags=["文档管理"])
app.include_router(config.router, prefix="/api", tags=["配置管理"])
app.include_router(logs.router, prefix="/api", tags=["日志管理"])


if __name__ == "__main__":
    # PyInstaller 多进程支持 - 必须在任何其他操作之前调用
    import multiprocessing
    multiprocessing.freeze_support()
    
    # 设置多进程启动方法为 spawn，避免 fork 导致的问题（特别是在 macOS 上）
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass  # 已经设置过了
    
    # print 重定向已在模块级别设置
    # 注意：uvicorn 会重新导入 main 模块，去重机制会避免重复日志
    
    import uvicorn
    import signal
    import sys
    import subprocess
    from pathlib import Path
    
    # 启动前执行清理
    print("🧹 启动前清理环境...")
    backend_dir = Path(__file__).parent
    cleanup_script = backend_dir / "cleanup.py"
    if cleanup_script.exists():
        try:
            subprocess.run([sys.executable, str(cleanup_script)], check=False, timeout=30)
            print()
        except Exception as e:
            print(f"⚠️ 清理脚本执行失败: {e}\n")
    
    host = os.getenv("HOST", "127.0.0.1")  # 默认只监听本地，更安全
    port = int(os.getenv("PORT", "8000"))
    
    # 检查端口是否被占用
    if not check_port_available(host, port):
        print(f"⚠️ 端口 {port} 已被占用")
        print(f"   可能的原因:")
        print(f"   1. 后端服务已在运行（这是正常的，无需重复启动）")
        print(f"   2. 其他程序占用了该端口")
        print(f"")
        print(f"   如果需要重启服务，请先停止现有服务：")
        print(f"   - 按 Ctrl+C 停止当前运行的服务")
        print(f"   - 或使用: lsof -ti:{port} | xargs kill -9")
        sys.exit(1)
    
    # 全局变量存储 uvicorn 服务器实例
    server_instance = None
    
    def signal_handler(sig, frame):
        """信号处理函数，确保优雅退出"""
        if is_shutdown_done():
            return  # 防止重复执行
        mark_shutdown_done()
        
        print(f"\n🛑 接收到信号 {sig}，正在关闭服务...")
        
        # 停止 RustFS 服务
        try:
            from services.rustfs_storage import stop_rustfs_server
            stop_rustfs_server()
            print("✅ RustFS 存储服务已停止")
        except Exception as e:
            print(f"⚠️ RustFS 停止警告: {e}")
        
        # 停止嵌入式 PostgreSQL（仅在使用嵌入式模式时）
        USE_EMBEDDED_PG = os.getenv("USE_EMBEDDED_PG", "true").lower() == "true"
        if USE_EMBEDDED_PG:
            try:
                from core.postgres_manager import get_postgres_manager
                pg_manager = get_postgres_manager()
                pg_manager.stop()
                print("✅ PostgreSQL 已停止")
            except Exception as e:
                print(f"⚠️ PostgreSQL 停止警告: {e}")
        
        print("👋 服务已关闭")
        sys.exit(0)
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # kill 命令
    
    print(f"🌐 服务将运行在: http://{host}:{port}")
    
    try:
        # 使用 app 对象直接运行（PyInstaller 兼容模式）
        # 字符串 "main:app" 在 PyInstaller 打包后可能无法正确导入
        uvicorn.run(
            app,
            host=host,
            port=port,
            reload=False,  # 生产环境关闭热重载
            log_level="info",
            log_config=None  # 禁用 uvicorn 的日志配置，使用我们的自定义日志
        )
    except KeyboardInterrupt:
        # 键盘中断已在 signal_handler 中处理
        pass
    except Exception as e:
        import traceback
        print(f"❌ 服务运行错误: {e}")
        print(f"详细错误:\n{traceback.format_exc()}")
        # 确保清理资源
        signal_handler(signal.SIGTERM, None)
