"""
后端主入口 - Python + Langchain + FastAPI
由 Electron 统一管理 PostgreSQL 和 RustFS 生命周期
"""
import asyncio
import os
import sys
import time
from pathlib import Path

# 导入公共工具模块
from utils import DatabaseConfig, test_connection_with_retry, print_db_config
from utils import resolve_path, check_executable, check_subdir, get_default_dir


def check_port_available(host: str, port: int) -> bool:
    """检查端口是否可用（未被占用）"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result != 0
    except:
        return False


def check_port_ready(host: str, port: int) -> bool:
    """检查端口是否已就绪（服务已启动并可连接）"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result == 0
    except:
        return False


async def wait_for_service(name: str, host: str, port: int, timeout: float = 60.0, interval: float = 0.5) -> bool:
    """等待服务端口就绪
    
    Args:
        name: 服务名称（用于日志）
        host: 主机地址
        port: 端口号
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）
    
    Returns:
        是否成功就绪
    """
    import asyncio
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if check_port_ready(host, port):
            return True
        await asyncio.sleep(interval)
    
    return False


# 获取 .env 文件路径
def get_env_file_path() -> Path:
    user_data_dir = get_default_dir('')
    user_env_path = user_data_dir / ".env"
    
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        bundled_path = exe_dir / ".env"
        
        if not user_env_path.exists() and bundled_path.exists():
            user_data_dir.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(bundled_path, user_env_path)
        
        return user_env_path if user_env_path.exists() else bundled_path
    
    dev_path = Path(__file__).parent / ".env"
    if dev_path.exists():
        return dev_path
    
    return user_env_path if user_env_path.exists() else dev_path


# 加载 .env 文件
from dotenv import load_dotenv
env_path = get_env_file_path()
if env_path.exists():
    load_dotenv(env_path, override=True)


# 设置默认目录
def get_default_user_dir(subdir: str) -> Path:
    if os.name == 'nt':
        base_dir = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif os.uname().sysname == 'Darwin':
        base_dir = Path.home() / 'Library' / 'Application Support'
    else:
        base_dir = Path(os.path.join(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')))
    return base_dir / 'Uverse' / subdir


if not os.getenv('TEMP_DIR'):
    default_temp = get_default_user_dir('temp')
    os.environ['TEMP_DIR'] = str(default_temp)
    default_temp.mkdir(parents=True, exist_ok=True)

if not os.getenv('MINERU_OUTPUT_DIR'):
    default_output = get_default_user_dir('outputs')
    os.environ['MINERU_OUTPUT_DIR'] = str(default_output)
    default_output.mkdir(parents=True, exist_ok=True)


# 初始化文件日志管理器
from core.file_logger import get_file_log_manager
file_log_manager = get_file_log_manager()


# 设置 logging 处理器
import logging


class FileLogHandler(logging.Handler):
    """将日志写入文件的处理器"""
    
    BLACKLIST_SOURCES = [
        'uvicorn', 'uvicorn.error', 'uvicorn.access', 'uvicorn.protocols',
        'fastapi', 'starlette', 'websockets', 'asyncio',
        'sqlalchemy', 'sqlalchemy.engine', 'sqlalchemy.pool',
        'botocore', 'boto3', 'urllib3', 'requests',
        'httpcore', 'httpx', 'aiosqlite',
        'PIL', 'matplotlib', 'numpy'
    ]
    
    SKIP_MESSAGES = [
        'TEXT', 'BYTES', 'ping', 'pong',
        'Application startup complete', 'Started server process',
        'Waiting for application', 'Application shutdown complete',
        'connection open', 'connection closed',
        '> ', '< ',
        'GET /', 'POST /', 'PUT /', 'DELETE /', 'OPTIONS /',
    ]
    
    def emit(self, record):
        try:
            for blacklisted in self.BLACKLIST_SOURCES:
                if record.name.startswith(blacklisted):
                    if record.levelno < logging.ERROR:
                        return
            
            msg = record.getMessage()
            for skip_pattern in self.SKIP_MESSAGES:
                if skip_pattern in msg:
                    return
            
            if len(msg) > 500 and ('{"type"' in msg or 'ping' in msg.lower()):
                return
            
            file_log_manager.add_log(
                level=record.levelname,
                message=msg,
                source=record.name
            )
        except Exception:
            self.handleError(record)


root_logger = logging.getLogger()

# 清理可能存在的默认 StreamHandler（避免控制台重复输出）
for h in root_logger.handlers[:]:
    if isinstance(h, logging.StreamHandler) and not isinstance(h, FileLogHandler):
        root_logger.removeHandler(h)

file_handler = None
for h in root_logger.handlers:
    if isinstance(h, FileLogHandler):
        file_handler = h
        break

if file_handler is None:
    file_handler = FileLogHandler()
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

root_logger.setLevel(logging.INFO)

# 配置应用 logger，但不添加额外 handler（避免重复）
# 所有日志通过 root_logger 的 FileLogHandler 统一处理
app_loggers = ['routers', 'services', 'core', 'models', '__main__']
for logger_name in app_loggers:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    # 不添加 handler，让日志传播到 root_logger 统一处理
    # 这样可以避免重复日志


# 重定向 print 到 logging
import sys

_original_stdout = sys.stdout
_original_stderr = sys.stderr

_main_module = sys.modules.get('__main__')

if _main_module and hasattr(_main_module, '_print_log_seen_messages') and _main_module._print_log_seen_messages is not None:
    _print_log_seen_messages = _main_module._print_log_seen_messages
else:
    _print_log_seen_messages = set()
    if _main_module:
        _main_module._print_log_seen_messages = _print_log_seen_messages


class PrintToLog:
    def __init__(self, logger_name='__main__'):
        self.logger = logging.getLogger(logger_name)
        self._buffer = ''
        self._seen = _print_log_seen_messages
    
    def write(self, message):
        self._buffer += message
        
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            line = line.rstrip()
            if line:
                self._emit_line(line)
    
    def _emit_line(self, line):
        if line in self._seen:
            return
        self._seen.add(line)
        
        if len(self._seen) > 1000:
            self._seen.clear()
        
        level = logging.INFO
        if '[ERROR]' in line or '错误' in line or 'Error' in line:
            level = logging.ERROR
        elif '[WARN]' in line or '警告' in line or 'Warning' in line:
            level = logging.WARNING
        
        self.logger.log(level, line)
    
    def flush(self):
        # 注意：不要直接发送 _buffer，因为它可能已经通过 write() 的部分内容处理过了
        # 只清空缓冲区，避免在程序退出时重复发送
        self._buffer = ''


_print_redirector = PrintToLog('__main__')
sys.stdout = _print_redirector
sys.stderr = _print_redirector


# 全局标志位
STORE_AVAILABLE = False
POSTGRES_AVAILABLE = False
MODELS_AVAILABLE = False


# 使用 sys.modules 存储跨模块实例的全局状态
_main_module = sys.modules.get('__main__')
if _main_module and not hasattr(_main_module, '_uvicorn_startup_done'):
    _main_module._uvicorn_startup_done = False
    _main_module._uvicorn_shutdown_done = False


def is_startup_done() -> bool:
    _main = sys.modules.get('__main__')
    return getattr(_main, '_uvicorn_startup_done', False) if _main else False


def mark_startup_done():
    _main = sys.modules.get('__main__')
    if _main:
        _main._uvicorn_startup_done = True


def is_shutdown_done() -> bool:
    _main = sys.modules.get('__main__')
    return getattr(_main, '_uvicorn_shutdown_done', False) if _main else False


def mark_shutdown_done():
    _main = sys.modules.get('__main__')
    if _main:
        _main._uvicorn_shutdown_done = True


# 导入 FastAPI
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# 导入路由
from routers import chat, documents, health, config, logs


_background_init_started = False
_background_init_completed = False


async def _background_init_services():
    """后台初始化服务 - 不阻塞启动"""
    global STORE_AVAILABLE, POSTGRES_AVAILABLE, MODELS_AVAILABLE
    global _background_init_started, _background_init_completed
    
    if _background_init_started:
        return
    _background_init_started = True
    
    try:
        backend_dir = Path(__file__).parent
        
        # 检查必要文件/目录
        store_dir = resolve_path(os.getenv("STORE_DIR", ""), backend_dir)
        models_dir = resolve_path(os.getenv("MODELS_DIR", ""), backend_dir)
        
        # 获取服务端口
        pg_port = int(os.getenv('PG_PORT', '15432'))
        
        # 解析 RustFS 端口（从 RUSTFS_URL 或 RUSTFS_PORT 环境变量）
        rustfs_port = 9000  # 默认值
        rustfs_url = os.getenv('RUSTFS_URL', '')
        if rustfs_url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(rustfs_url)
                if parsed.port:
                    rustfs_port = parsed.port
            except:
                pass
        if os.getenv('RUSTFS_PORT'):
            rustfs_port = int(os.getenv('RUSTFS_PORT'))
        
        # 检查 RustFS 可执行文件
        if store_dir:
            # 根据平台选择正确的可执行文件名
            rustfs_binary = 'rustfs.exe' if os.name == 'nt' else 'rustfs'
            rustfs_exe = store_dir / rustfs_binary
            STORE_AVAILABLE = rustfs_exe.exists()
            print(f"[OK] RustFS 可执行文件: {rustfs_exe}" if STORE_AVAILABLE else f"[WARN] RustFS 可执行文件不存在: {rustfs_exe}")
        else:
            STORE_AVAILABLE = False
            print("[WARN] STORE_DIR 未配置")
        
        # 检查 Models 目录
        if models_dir:
            MODELS_AVAILABLE = (models_dir / 'OpenDataLab').exists()
            print(f"[OK] Models 目录: {models_dir}" if MODELS_AVAILABLE else f"[WARN] Models/OpenDataLab 不存在: {models_dir}")
        else:
            MODELS_AVAILABLE = False
            print("[WARN] MODELS_DIR 未配置")
        
        # 等待 PostgreSQL 就绪
        print(f"[WAIT] 等待 PostgreSQL 在端口 {pg_port} 就绪...")
        pg_ready = await wait_for_service("PostgreSQL", "127.0.0.1", pg_port, timeout=60.0)
        if not pg_ready:
            print(f"[ERROR] PostgreSQL 在 {pg_port} 端口未就绪，超时")
            POSTGRES_AVAILABLE = False
            _background_init_completed = True
            return
        print(f"[OK] PostgreSQL 已就绪 (端口 {pg_port})")
        
        # 等待 RustFS 就绪
        print(f"[WAIT] 等待 RustFS 在端口 {rustfs_port} 就绪...")
        rustfs_ready = await wait_for_service("RustFS", "127.0.0.1", rustfs_port, timeout=30.0)
        if not rustfs_ready:
            print(f"[WARN] RustFS 在 {rustfs_port} 端口未就绪，存储功能将不可用")
            STORE_AVAILABLE = False
        else:
            print(f"[OK] RustFS 已就绪 (端口 {rustfs_port})")
        
        # 初始化数据库连接（外部 PG，由 Electron 管理）
        print("[INIT] 初始化数据库连接...")
        os.environ["DATABASE_URL"] = f"postgresql://postgres@127.0.0.1:{pg_port}/postgres"
        
        # 先导入所有模型，确保表被注册到 Base.metadata
        from core.storage import StorageRecord  # noqa: F401 - 导入以注册模型
        
        # 测试数据库连接
        from core.database import init_engine
        init_engine()
        
        # 检查表
        from sqlalchemy import inspect
        from core.database import get_engine, Base
        
        try:
            engine = get_engine()
            async with engine.connect() as conn:
                def check_tables(sync_conn):
                    inspector = inspect(sync_conn)
                    return inspector.get_table_names()
                
                table_names = await conn.run_sync(check_tables)
                required_tables = ['storage_records']
                missing_tables = [t for t in required_tables if t not in table_names]
                
                if missing_tables:
                    print(f"[WARN] 数据库表不存在: {', '.join(missing_tables)}，正在自动创建...")
                    try:
                        await conn.run_sync(Base.metadata.create_all)
                        await conn.commit()
                        print(f"[OK] 数据库表创建完成")
                    except Exception as create_error:
                        print(f"[ERROR] 自动创建数据库表失败: {create_error}")
                else:
                    print(f"[OK] 数据库表检查通过，共 {len(table_names)} 个表")
        except Exception as e:
            print(f"[ERROR] 检查数据库表失败: {e}")
        
        POSTGRES_AVAILABLE = True
        
        # 初始化存储桶（RustFS 已由 Electron 启动，且已通过端口检测）
        if STORE_AVAILABLE and rustfs_ready:
            try:
                from services.rustfs_storage import RustFSStorage
                storage = RustFSStorage()
                storage._init_buckets()
                print("[OK] RustFS 存储桶初始化完成")
            except Exception as e:
                print(f"[WARN] RustFS 初始化失败: {e}")
                STORE_AVAILABLE = False
        
        # 预加载 MinerU
        if MODELS_AVAILABLE:
            import threading
            def preload_mineru():
                try:
                    print("[WAIT] 预加载 MinerU 模块...")
                    from services.pdf_parser import get_pdf_parser
                    print("[OK] MinerU 模块预加载完成")
                except Exception as e:
                    print(f"[WARN] MinerU 预加载失败: {e}")
            threading.Thread(target=preload_mineru, daemon=True).start()
        
        _background_init_completed = True
        print("[OK] 后台初始化完成")
    except Exception as e:
        print(f"[ERROR] 后台初始化异常: {e}")
        import traceback
        traceback.print_exc()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    import asyncio
    
    _main = sys.modules.get('__main__')
    
    loop = asyncio.get_event_loop()
    file_log_manager.set_event_loop(loop)
    
    if is_startup_done():
        print("[START] 后端服务启动中... (跳过重复执行)")
        yield
        return
    mark_startup_done()
    
    print("[START] 后端服务启动中...")
    asyncio.create_task(_background_init_services())
    
    yield
    
    if is_shutdown_done():
        return
    mark_shutdown_done()
    
    print("[BYE] 后端服务正在关闭...")
    
    # 等待活跃任务
    try:
        from routers.documents import _active_tasks
        if _active_tasks:
            print(f"[WAIT] 等待 {_active_tasks} 个活跃解析任务完成...")
            for _ in range(30):
                if not _active_tasks:
                    break
                await asyncio.sleep(1)
            if _active_tasks:
                print(f"[WARN] 仍有 {_active_tasks} 个任务未完成，强制关闭")
    except Exception as e:
        print(f"[WARN] 等待任务完成时出错: {e}")
    
    # 关闭进程池
    try:
        from workers.pool import shutdown_process_pool
        shutdown_process_pool()
        print("[OK] PDF 解析进程池已关闭")
    except Exception as e:
        print(f"[WARN] 进程池关闭警告: {e}")
    
    print("[BYE] 后端服务已关闭")


app = FastAPI(
    title="知识库 API",
    description="知识库后端服务",
    version="0.1.0",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    # PyInstaller 多进程支持
    import multiprocessing
    multiprocessing.freeze_support()
    
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass
    
    import uvicorn
    import signal
    
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    
    # 检查端口是否被占用
    if not check_port_available(host, port):
        print(f"[WARN] 端口 {port} 已被占用，后端服务可能已在运行")
        sys.exit(1)
    
    print(f"[WEB] 服务将运行在: http://{host}:{port}")
    
    # 配置 uvicorn 日志，避免重复输出
    # uvicorn 的日志应该传播到 root_logger，由 FileLogHandler 统一处理
    import logging.config
    uvicorn_log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {},
        "loggers": {
            "uvicorn": {"handlers": [], "level": "INFO", "propagate": True},
            "uvicorn.error": {"handlers": [], "level": "INFO", "propagate": True},
            "uvicorn.access": {"handlers": [], "level": "INFO", "propagate": True},
        },
    }
    
    exit_code = 0
    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            reload=False,
            log_level="info",
            log_config=uvicorn_log_config
        )
    except KeyboardInterrupt:
        pass
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else 0
    except Exception as e:
        import traceback
        print(f"[ERROR] 服务运行错误: {e}")
        print(f"详细错误:\n{traceback.format_exc()}")
        exit_code = 1
    
    sys.exit(exit_code)
