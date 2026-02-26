"""
PDF 解析进程池 - 使用子进程执行 MinerU 解析

核心设计：通过独立子进程执行 MinerU，可以强制终止，实现真正的取消功能。
日志直接写入文件，前端通过 API 轮询读取。
"""
import os
import sys
import asyncio
import json
import threading
import logging
import subprocess
import signal
import tempfile
import platform
from typing import Dict, Optional, Any
from pathlib import Path

# 获取 logger
logger = logging.getLogger(__name__)

# 存储正在运行的子进程：task_id -> subprocess.Popen
_running_processes: Dict[str, subprocess.Popen] = {}
_process_lock = threading.Lock()


def _get_log_dir(log_dir_name: str = "logs") -> Path:
    """获取日志目录路径 - 与 ParseFileLogger 保持一致
    
    开发模式：使用项目目录的 backend/logs
    打包模式：使用用户可写目录 (support/userData)
    """
    # 开发环境：使用项目目录
    if not getattr(sys, 'frozen', False):
        return Path(__file__).parent.parent / log_dir_name
    
    # 打包环境：使用用户可写目录
    if _IS_WINDOWS:
        base_dir = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif sys.platform == 'darwin':  # macOS
        base_dir = Path.home() / 'Library' / 'Application Support'
    else:  # Linux
        base_dir = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    
    return base_dir / 'Uverse' / log_dir_name

# 取消信号文件目录（用于跨进程通信）
_cancel_signal_dir: Optional[Path] = None

# 判断是否在 Windows 上
_IS_WINDOWS = platform.system() == "Windows"


def _get_cancel_signal_path(task_id: str) -> Path:
    """获取取消信号文件路径"""
    global _cancel_signal_dir
    if _cancel_signal_dir is None:
        _cancel_signal_dir = Path(tempfile.gettempdir()) / "uverse_cancel_signals"
        _cancel_signal_dir.mkdir(parents=True, exist_ok=True)
    return _cancel_signal_dir / f"cancel_{task_id}.signal"


def _set_cancel_signal(task_id: str):
    """设置取消信号（创建信号文件）"""
    signal_path = _get_cancel_signal_path(task_id)
    signal_path.touch(exist_ok=True)
    logger.info(f"[ProcessPool] 已设置取消信号: {signal_path}")


def _clear_cancel_signal(task_id: str):
    """清除取消信号（删除信号文件）"""
    signal_path = _get_cancel_signal_path(task_id)
    if signal_path.exists():
        signal_path.unlink()


def _kill_process_tree(process: subprocess.Popen) -> bool:
    """终止进程及其子进程树"""
    if process.poll() is not None:
        return True
    
    pid = process.pid
    
    try:
        if _IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=5
            )
        else:
            pgid = os.getpgid(pid)
            try:
                os.killpg(pgid, signal.SIGTERM)
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    os.killpg(pgid, signal.SIGKILL)
                    process.wait(timeout=1)
        
        # 确保进程已终止
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=2)
        return True
        
    except (ProcessLookupError, subprocess.TimeoutExpired):
        return True
    except Exception as e:
        logger.error(f"[ProcessPool] 终止进程失败: {e}")
        try:
            process.kill()
            return True
        except:
            return False


def stop_parse_process(task_id: str) -> bool:
    """强制停止解析进程"""
    logger.info(f"[ProcessPool] 尝试停止任务 {task_id}")
    _set_cancel_signal(task_id)
    
    with _process_lock:
        if task_id in _running_processes:
            process = _running_processes[task_id]
            logger.info(f"[ProcessPool] 终止进程 PID {process.pid}")
            return _kill_process_tree(process)
    
    logger.info(f"[ProcessPool] 未找到运行中的进程 {task_id}")
    return False


def _get_worker_executable() -> Optional[Path]:
    """获取 PDF Worker 可执行文件路径（打包环境下使用）"""
    # 首先检查当前可执行文件所在目录（适用于 PyInstaller 打包模式）
    exe_dir = Path(sys.executable).parent
    worker_path = exe_dir / ('pdf-worker.exe' if _IS_WINDOWS else 'pdf-worker')
    
    if worker_path.exists():
        logger.info(f"[ProcessPool] 找到 PDF Worker: {worker_path}")
        return worker_path
    
    # 如果是 PyInstaller 打包模式，尝试 _MEIPASS
    if hasattr(sys, '_MEIPASS'):
        alt_path = Path(sys._MEIPASS) / ('pdf-worker.exe' if _IS_WINDOWS else 'pdf-worker')
        if alt_path.exists():
            logger.info(f"[ProcessPool] 找到 PDF Worker (_MEIPASS): {alt_path}")
            return alt_path
    
    # 尝试 backend 目录（Electron 打包模式）
    backend_dir = _get_backend_dir()
    backend_worker = backend_dir / ('pdf-worker.exe' if _IS_WINDOWS else 'pdf-worker')
    if backend_worker.exists():
        logger.info(f"[ProcessPool] 找到 PDF Worker (backend): {backend_worker}")
        return backend_worker
    
    logger.warning("[ProcessPool] 未找到 pdf-worker")
    return None


def _get_python_executable() -> str:
    """获取 Python 解释器路径"""
    if not hasattr(sys, '_MEIPASS'):
        return sys.executable
    
    import shutil
    
    # 优先找系统 Python
    system_paths = [
        '/usr/bin/python3', '/usr/local/bin/python3',
        '/opt/homebrew/bin/python3', '/opt/local/bin/python3',
        shutil.which('python3'), shutil.which('python')
    ]
    
    for python_path in system_paths:
        if python_path and os.path.exists(python_path) and '.venv' not in python_path:
            return python_path
    
    logger.error("[ProcessPool] 打包模式，未找到合适的系统 Python")
    return sys.executable


def _get_backend_dir() -> Path:
    """获取 backend 目录路径 - 兼容打包模式"""
    if hasattr(sys, '_MEIPASS'):
        exe_dir = Path(sys.executable).parent
        return exe_dir.parent if "_internal" in str(exe_dir) else exe_dir
    return Path(__file__).parent.parent


def _get_wrapper_script_path() -> Path:
    """获取 wrapper 脚本路径"""
    backend_dir = _get_backend_dir()
    
    if hasattr(sys, '_MEIPASS'):
        # 打包模式下尝试多个路径
        exe_dir = Path(sys.executable).parent
        for base in [exe_dir, exe_dir.parent, Path(sys._MEIPASS), Path(sys._MEIPASS).parent]:
            path = base / "workers" / "pdf_wrapper.py"
            if path.exists():
                return path
    
    return backend_dir / "workers" / "pdf_wrapper.py"


def _build_command(
    pdf_path: str, output_dir: str, config_path: str,
    doc_id: str, task_id: str, log_file: Path,
    device: str, cancel_signal_path: Path,
    filename: Optional[str]
) -> tuple[list[str], str]:
    """构建子进程命令"""
    worker_exe = _get_worker_executable()
    
    base_args = [
        "--pdf-path", pdf_path,
        "--output-dir", output_dir,
        "--config-path", config_path,
        "--doc-id", doc_id,
        "--task-id", task_id,
        "--log-file", str(log_file.resolve()),
        "--device", device,
        "--cancel-check-file", str(cancel_signal_path),
    ]
    if filename:
        base_args.extend(["--filename", filename])
    
    if worker_exe:
        return [str(worker_exe)] + base_args, str(worker_exe.parent)
    else:
        return [sys.executable, str(_get_wrapper_script_path())] + base_args, str(_get_backend_dir())


def _get_subprocess_startup_args() -> tuple[Optional[Any], Optional[Any]]:
    """获取子进程启动参数（跨平台）"""
    if _IS_WINDOWS:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        return startupinfo, None
    return None, os.setsid


def _read_pipe(pipe, buffer: list, lock: threading.Lock, stop_event: threading.Event, log_prefix: str = ""):
    """后台线程读取管道（stdout/stderr）"""
    if not pipe:
        return
    
    try:
        while not stop_event.is_set():
            line = pipe.readline()
            if not line:
                break
            try:
                line_str = line.decode('utf-8').strip()
                if line_str:
                    with lock:
                        buffer.append(line_str)
                    if log_prefix:
                        logger.info(f"[{log_prefix}] {line_str}")
            except Exception:
                pass
    except Exception:
        pass


async def parse_pdf_in_process(
    pdf_path: str,
    doc_id: str,
    task_id: str,
    output_dir: str,
    config_path: str,
    device: str = "cpu",
    backend: str = "pipeline",
    filename: str = None
) -> Dict[str, Any]:
    """
    使用子进程执行 PDF 解析
    日志直接写入文件，不通过 stderr 捕获
    """
    logger.info(f"[ProcessPool] 开始解析任务 {task_id}")
    
    # 清理之前的取消信号
    _clear_cancel_signal(task_id)
    cancel_signal_path = _get_cancel_signal_path(task_id)
    
    # 日志文件路径 - 使用与 ParseFileLogger 一致的目录
    log_file = _get_log_dir("logs") / "parse" / f"{task_id}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 构建命令
    cmd, cwd = _build_command(
        pdf_path, output_dir, config_path,
        doc_id, task_id, log_file,
        device, cancel_signal_path, filename
    )
    logger.info(f"[ProcessPool] 启动子进程: {cmd}")
    
    # 设置环境变量
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'}
    startupinfo, preexec_fn = _get_subprocess_startup_args()
    
    # 启动子进程
    logger.info(f"[ProcessPool] 工作目录: {cwd}")
    logger.info(f"[ProcessPool] 命令: {' '.join(cmd)}")
    
    # 检查命令是否存在
    if not Path(cmd[0]).exists():
        logger.error(f"[ProcessPool] 命令不存在: {cmd[0]}")
        return {"success": False, "error": f"解析程序不存在: {cmd[0]}"}
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            startupinfo=startupinfo,
            preexec_fn=preexec_fn,
            cwd=cwd,
            env=env
        )
        logger.info(f"[ProcessPool] 子进程已启动，PID: {process.pid}")
    except Exception as e:
        logger.error(f"[ProcessPool] 启动子进程失败: {e}")
        import traceback
        logger.error(f"[ProcessPool] 启动失败堆栈: {traceback.format_exc()}")
        return {"success": False, "error": f"启动解析进程失败: {e}"}
    
    # 记录进程
    with _process_lock:
        _running_processes[task_id] = process
    
    # 导入 parse_file_logger 用于写入任务日志
    from core.parse_file_logger import get_parse_file_logger
    parse_logger = get_parse_file_logger()
    
    # 用于后台读取的缓冲区和事件
    stop_event = threading.Event()
    stdout_buffer, stderr_buffer = [], []
    buffer_lock = threading.Lock()
    
    # 启动后台线程读取 stdout 和 stderr
    stdout_thread = threading.Thread(
        target=_read_pipe, 
        args=(process.stdout, stdout_buffer, buffer_lock, stop_event),
        daemon=True
    )
    stderr_thread = threading.Thread(
        target=_read_pipe,
        args=(process.stderr, stderr_buffer, buffer_lock, stop_event, "PDFWorker stderr"),
        daemon=True
    )
    stdout_thread.start()
    stderr_thread.start()
    
    try:
        # 等待子进程完成
        logger.info(f"[ProcessPool] 等待子进程 PID {process.pid} 完成...")
        
        while process.poll() is None:
            # 检查是否被取消
            try:
                from routers.documents import check_cancelled
                if check_cancelled(task_id):
                    logger.info("[ProcessPool] 检测到取消请求，终止子进程")
                    _kill_process_tree(process)
                    return {"success": False, "error": "任务已被用户取消", "cancelled": True}
            except Exception as e:
                logger.debug(f"[ProcessPool] 检查取消状态时出错: {e}")
            
            await asyncio.sleep(0.5)
        
        # 停止读取线程
        stop_event.set()
        parse_logger.flush_task_buffer(task_id)
        stdout_thread.join(timeout=2.0)
        stderr_thread.join(timeout=2.0)
        
        returncode = process.returncode
        
        # 从缓冲区获取 stdout
        with buffer_lock:
            stdout_lines = stdout_buffer[:]
        
        # 备用方案：直接读取剩余输出
        if not stdout_lines and process.stdout:
            try:
                remaining = process.stdout.read()
                if remaining:
                    stdout_text = remaining.decode('utf-8') if remaining else remaining.decode('gbk', errors='replace')
                    stdout_lines = [line.strip() for line in stdout_text.split('\n') if line.strip()]
            except Exception as e:
                logger.warning(f"[ProcessPool] 读取剩余 stdout 失败: {e}")
        
        logger.info(f"[ProcessPool] 进程返回码: {returncode}")
        logger.info(f"[ProcessPool] stdout 行数: {len(stdout_lines)}")
        logger.info(f"[ProcessPool] stderr 行数: {len(stderr_buffer)}")
        
        # 输出 stderr 内容用于诊断
        if stderr_buffer:
            logger.warning(f"[ProcessPool] stderr 输出:")
            for line in stderr_buffer[:20]:  # 只输出前20行
                logger.warning(f"  {line}")
        
        # 输出 stdout 内容用于诊断
        if stdout_lines:
            logger.info(f"[ProcessPool] stdout 输出 (前10行):")
            for line in stdout_lines[:10]:
                logger.info(f"  {line}")
        else:
            logger.warning(f"[ProcessPool] stdout 为空!")
        
        # 检查是否被取消
        if cancel_signal_path.exists():
            return {"success": False, "error": "任务已被用户取消", "cancelled": True}
        
        # 处理返回码
        if returncode != 0:
            error_msg = f"解析进程失败 (exit code: {returncode})"
            for line in reversed(stdout_lines):
                try:
                    result = json.loads(line)
                    if isinstance(result, dict) and "error" in result:
                        error_msg = result.get("error", error_msg)
                        break
                except json.JSONDecodeError:
                    continue
            
            parse_logger.add_log(task_id, "ERROR", error_msg)
            parse_logger.flush_task_buffer(task_id)
            return {"success": False, "error": error_msg}
        
        # 解析 stdout 获取结果
        logger.info(f"[ProcessPool] 尝试从 stdout 解析结果...")
        success_results = []  # 成功的结果
        error_results = []    # 失败的结果
        
        for i, line in enumerate(reversed(stdout_lines)):
            try:
                result = json.loads(line)
                if isinstance(result, dict) and "success" in result:
                    if result.get("success") is True:
                        success_results.append((i, result))
                    else:
                        error_results.append((i, result))
            except json.JSONDecodeError as e:
                logger.debug(f"[ProcessPool] 第 {i} 行不是有效 JSON: {e}")
                continue
        
        # 优先返回成功的结果
        if success_results:
            i, result = success_results[0]
            logger.info(f"[ProcessPool] 找到成功的结果在第 {i} 行")
            return result
        
        # 如果没有成功的，返回最后一个失败的结果
        if error_results:
            i, result = error_results[0]
            logger.warning(f"[ProcessPool] 未找到成功结果，返回第 {i} 行的失败结果: {result.get('error', '未知错误')}")
            return result
        
        # 诊断信息
        logger.error(f"[ProcessPool] 未找到包含 'success' 字段的 JSON 结果")
        logger.error(f"[ProcessPool] stdout 总行数: {len(stdout_lines)}")
        logger.error(f"[ProcessPool] stdout 内容:")
        for line in stdout_lines[:20]:
            logger.error(f"  {line}")
        
        return {"success": False, "error": "无法解析子进程输出: 未找到有效的结果"}
        
    except asyncio.CancelledError:
        logger.info("[ProcessPool] asyncio 任务被取消")
        _kill_process_tree(process)
        return {"success": False, "error": "任务已被取消", "cancelled": True}
        
    except Exception as e:
        logger.error(f"[ProcessPool] 解析过程异常: {e}")
        return {"success": False, "error": f"解析过程异常: {e}"}
        
    finally:
        with _process_lock:
            _running_processes.pop(task_id, None)
        _clear_cancel_signal(task_id)
        
        if process.poll() is None:
            logger.warning("[ProcessPool] 进程仍未终止，强制杀死")
            _kill_process_tree(process)
