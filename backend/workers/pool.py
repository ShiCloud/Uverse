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
    
    try:
        if _IS_WINDOWS:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    capture_output=True,
                    timeout=5
                )
                process.wait(timeout=2)
                return True
            except Exception as e:
                logger.error(f"[ProcessPool] Windows 终止进程失败: {e}")
                try:
                    process.terminate()
                    process.wait(timeout=2)
                except:
                    try:
                        process.kill()
                        process.wait(timeout=1)
                    except:
                        pass
                return True
        else:
            try:
                pgid = os.getpgid(process.pid)
                os.killpg(pgid, signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                    return True
                except subprocess.TimeoutExpired:
                    pass
                if process.poll() is None:
                    os.killpg(pgid, signal.SIGKILL)
                    process.wait(timeout=1)
                return True
            except ProcessLookupError:
                return True
            except Exception as e:
                logger.error(f"[ProcessPool] 终止进程组失败: {e}")
                try:
                    process.kill()
                    return True
                except:
                    return False
    except Exception as e:
        logger.error(f"[ProcessPool] 终止进程时出错: {e}")
        return False


def stop_parse_process(task_id: str) -> bool:
    """强制停止解析进程"""
    logger.info(f"[ProcessPool] 尝试停止任务 {task_id}")
    _set_cancel_signal(task_id)
    
    with _process_lock:
        if task_id in _running_processes:
            process = _running_processes[task_id]
            logger.info(f"[ProcessPool] 终止进程 PID {process.pid}")
            success = _kill_process_tree(process)
            return success
    
    logger.info(f"[ProcessPool] 未找到运行中的进程 {task_id}")
    return False


def _get_worker_executable() -> Optional[Path]:
    """获取 PDF Worker 可执行文件路径（打包环境下使用）"""
    if hasattr(sys, '_MEIPASS'):
        exe_dir = Path(sys.executable).parent
        worker_paths = [
            exe_dir / 'pdf-worker',
            Path(sys._MEIPASS) / 'pdf-worker',
        ]
        if _IS_WINDOWS:
            worker_paths = [p.with_suffix('.exe') for p in worker_paths]
        
        for worker_path in worker_paths:
            if worker_path.exists():
                logger.info(f"[ProcessPool] 找到 PDF Worker: {worker_path}")
                return worker_path
        
        logger.warning(f"[ProcessPool] 未找到 pdf-worker")
    return None


def _get_python_executable() -> str:
    """获取 Python 解释器路径"""
    if hasattr(sys, '_MEIPASS'):
        import shutil
        system_pythons = [
            '/usr/bin/python3',
            '/usr/local/bin/python3',
            '/opt/homebrew/bin/python3',
            '/opt/local/bin/python3',
        ]
        for python_path in system_pythons:
            if os.path.exists(python_path) and os.access(python_path, os.X_OK):
                return python_path
        
        python_cmd = shutil.which('python3')
        if python_cmd and '.venv' not in python_cmd:
            return python_cmd
        
        python_cmd = shutil.which('python')
        if python_cmd and '.venv' not in python_cmd:
            return python_cmd
        
        logger.error(f"[ProcessPool] 打包模式，未找到合适的系统 Python")
    return sys.executable


def _get_wrapper_script_path() -> Path:
    """获取 wrapper 脚本路径"""
    backend_dir = Path(__file__).parent.parent
    wrapper_path = backend_dir / "workers" / "pdf_wrapper.py"
    
    if wrapper_path.exists():
        return wrapper_path
    
    if hasattr(sys, '_MEIPASS'):
        # 打包模式下尝试多个路径
        exe_dir = Path(sys.executable).parent
        possible_paths = [
            exe_dir / "workers" / "pdf_wrapper.py",
            exe_dir.parent / "workers" / "pdf_wrapper.py",
            Path(sys._MEIPASS) / "workers" / "pdf_wrapper.py",
            Path(sys._MEIPASS).parent / "workers" / "pdf_wrapper.py",
        ]
        
        for path in possible_paths:
            if path.exists():
                return path
        
        # 如果没找到，返回第一个路径（让调用者处理错误）
        return possible_paths[0]
    
    return wrapper_path


def _get_backend_dir() -> Path:
    """获取 backend 目录路径 - 兼容打包模式"""
    # 打包模式 (PyInstaller)
    if hasattr(sys, '_MEIPASS'):
        # 尝试从可执行文件位置推导
        exe_dir = Path(sys.executable).parent
        # 如果在 _internal 目录中，向上查找
        if "_internal" in str(exe_dir):
            return exe_dir.parent
        return exe_dir
    
    # 开发模式：从当前文件 (workers/pool.py) 推导
    return Path(__file__).parent.parent


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
    
    # 日志文件路径（使用 task_id 命名，确保一致性）
    backend_dir = _get_backend_dir()
    log_file = backend_dir / "logs" / "parse" / f"{task_id}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 构建命令
    worker_exe = _get_worker_executable()
    
    if worker_exe:
        cmd = [
            str(worker_exe),
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
            cmd.extend(["--filename", filename])
        cwd = str(worker_exe.parent)
    else:
        python_exe = _get_python_executable()
        wrapper_script = _get_wrapper_script_path()
        
        cmd = [
            python_exe,
            str(wrapper_script),
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
            cmd.extend(["--filename", filename])
        cwd = str(_get_backend_dir()) if wrapper_script.exists() else str(Path.cwd())
    
    logger.info(f"[ProcessPool] 启动子进程: {cmd}")
    
    # 配置子进程启动参数
    startupinfo = None
    preexec_fn = None
    
    if _IS_WINDOWS:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
    else:
        preexec_fn = os.setsid
    
    # 设置环境变量
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    
    # 启动子进程（stdout 用于输出结果，stderr 捕获日志）
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # 捕获 stderr 用于日志
            text=False,   # 使用二进制模式，避免编码问题
            startupinfo=startupinfo,
            preexec_fn=preexec_fn,
            cwd=cwd,
            env=env
        )
    except Exception as e:
        logger.error(f"[ProcessPool] 启动子进程失败: {e}")
        return {
            "success": False,
            "error": f"启动解析进程失败: {e}",
        }
    
    # 记录进程
    with _process_lock:
        _running_processes[task_id] = process
    
    # 导入 parse_file_logger 用于写入任务日志
    from core.parse_file_logger import get_parse_file_logger
    parse_logger = get_parse_file_logger()
    
    # 用于收集子进程输出的线程
    stderr_lines = []
    stderr_buffer_queue = []  # 缓冲区队列
    stderr_buffer_lock = threading.Lock()
    stderr_stop_event = threading.Event()
    
    # 收集 stdout 的缓冲区（关键：防止 stdout 缓冲区满导致死锁）
    stdout_buffer = []
    stdout_buffer_lock = threading.Lock()
    
    def read_stderr():
        """在后台线程读取子进程 stderr 并写入缓冲区"""
        nonlocal stderr_buffer_queue
        if process.stderr:
            try:
                # 使用更大的缓冲区读取
                while not stderr_stop_event.is_set():
                    line = process.stderr.readline()
                    if not line:
                        break
                    try:
                        line_str = line.decode('utf-8').strip()
                        if line_str:
                            with stderr_buffer_lock:
                                stderr_lines.append(line_str)
                                stderr_buffer_queue.append(line_str)
                    except Exception:
                        pass
            except Exception:
                pass
    
    def read_stdout():
        """在后台线程读取子进程 stdout - 防止缓冲区满导致死锁"""
        nonlocal stdout_buffer
        if process.stdout:
            try:
                while not stderr_stop_event.is_set():
                    line = process.stdout.readline()
                    if not line:
                        break
                    try:
                        line_str = line.decode('utf-8').strip()
                        if line_str:
                            with stdout_buffer_lock:
                                stdout_buffer.append(line_str)
                            # 同时处理日志行（打包模式下 pdf_wrapper 输出日志到 stdout）
                            _process_log_line(line_str)
                    except Exception:
                        pass
            except Exception:
                pass
    
    def _process_log_line(line_str: str):
        """处理日志行 - 从 stdout/stderr 提取日志并写入文件"""
        try:
            # 解析日志级别和内容（格式: [LEVEL] message）
            if line_str.startswith('[') and ']' in line_str:
                level_end = line_str.find(']')
                level = line_str[1:level_end]
                msg = line_str[level_end+1:].strip()
                if level in ['INFO', 'WARNING', 'ERROR', 'DEBUG']:
                    # 写入任务日志文件
                    parse_logger.add_log(task_id, level, msg)
                    # 同时输出到后端日志
                    logger.info(f"[PDFWorker] {msg}")
                else:
                    # 不是标准日志级别，但作为 INFO 记录
                    parse_logger.add_log(task_id, 'INFO', line_str)
                    logger.info(f"[PDFWorker] {line_str}")
        except Exception:
            pass
    
    def process_stderr_buffer():
        """处理 stderr 缓冲区中的日志行"""
        nonlocal stderr_buffer_queue
        with stderr_buffer_lock:
            if not stderr_buffer_queue:
                return
            # 复制并清空缓冲区
            lines_to_process = stderr_buffer_queue[:]
            stderr_buffer_queue = []
        
        # 在锁外处理日志，减少锁持有时间
        for line_str in lines_to_process:
            _process_log_line(line_str)
    
    # 启动后台线程读取 stdout 和 stderr（关键：必须同时读取，防止死锁）
    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    
    try:
        # 等待子进程完成
        logger.info(f"[ProcessPool] 等待子进程 PID {process.pid} 完成...")
        
        check_interval = 0.5
        while True:
            # 检查进程是否结束
            if process.poll() is not None:
                break
            
            # 检查是否被取消
            try:
                from routers.documents import check_cancelled
                if check_cancelled(task_id):
                    logger.info(f"[ProcessPool] 检测到取消请求，终止子进程")
                    _kill_process_tree(process)
                    try:
                        process.wait(timeout=5.0)
                    except:
                        pass
                    return {
                        "success": False,
                        "error": "任务已被用户取消",
                        "cancelled": True
                    }
            except Exception as e:
                logger.debug(f"[ProcessPool] 检查取消状态时出错: {e}")
            
            # 定期处理 stderr 缓冲区
            process_stderr_buffer()
            
            await asyncio.sleep(check_interval)
        
        # 停止读取线程
        stderr_stop_event.set()
        # 最后处理一次缓冲区
        process_stderr_buffer()
        # 刷新日志缓冲区
        parse_logger.flush_task_buffer(task_id)
        # 等待读取线程结束
        stdout_thread.join(timeout=2.0)
        stderr_thread.join(timeout=2.0)
        
        # 获取返回码和 stdout
        returncode = process.returncode
        
        # 从缓冲区获取 stdout（已经从后台线程读取）
        with stdout_buffer_lock:
            stdout_lines = stdout_buffer[:]
        
        # 如果缓冲区为空，尝试直接读取（备用方案）
        if not stdout_lines and process.stdout:
            try:
                remaining = process.stdout.read()
                if remaining:
                    try:
                        stdout_text = remaining.decode('utf-8')
                    except UnicodeDecodeError:
                        stdout_text = remaining.decode('gbk', errors='replace')
                    stdout_lines = [line.strip() for line in stdout_text.strip().split('\n') if line.strip()]
            except Exception as e:
                logger.warning(f"[ProcessPool] 读取剩余 stdout 失败: {e}")
        
        logger.info(f"[ProcessPool] 进程返回码: {returncode}")
        
        # 检查是否被取消
        if _get_cancel_signal_path(task_id).exists():
            return {
                "success": False,
                "error": "任务已被用户取消",
                "cancelled": True
            }
        
        # 检查返回码
        if returncode != 0:
            error_msg = f"解析进程失败 (exit code: {returncode})"
            # 尝试从 stdout 解析错误
            for line in reversed(stdout_lines):
                line = line.strip()
                if line:
                    try:
                        result = json.loads(line)
                        if isinstance(result, dict) and "error" in result:
                            error_msg = result.get("error", error_msg)
                            break
                    except json.JSONDecodeError:
                        continue
            
            # 记录错误到日志
            parse_logger.add_log(task_id, "ERROR", error_msg)
            # 如果有 stderr 输出，也记录到日志
            for line in stderr_lines[-20:]:  # 记录最后20行stderr
                if line:
                    parse_logger.add_log(task_id, "ERROR", f"STDERR: {line}")
            parse_logger.flush_task_buffer(task_id)
            
            return {
                "success": False,
                "error": error_msg,
            }
        
        # 解析 stdout 获取结果
        for line in reversed(stdout_lines):
            line = line.strip()
            if line:
                try:
                    result = json.loads(line)
                    if isinstance(result, dict) and "success" in result:
                        return result
                except json.JSONDecodeError:
                    continue
        
        return {
            "success": False,
            "error": "无法解析子进程输出",
        }
        
    except asyncio.CancelledError:
        logger.info(f"[ProcessPool] asyncio 任务被取消")
        _kill_process_tree(process)
        return {
            "success": False,
            "error": "任务已被取消",
            "cancelled": True
        }
        
    except Exception as e:
        logger.error(f"[ProcessPool] 解析过程异常: {e}")
        return {
            "success": False,
            "error": f"解析过程异常: {e}",
        }
        
    finally:
        # 从字典中移除
        with _process_lock:
            _running_processes.pop(task_id, None)
        
        # 清理取消信号
        _clear_cancel_signal(task_id)
        
        # 确保进程已终止
        if process.poll() is None:
            logger.warning(f"[ProcessPool] 进程仍未终止，强制杀死")
            _kill_process_tree(process)
