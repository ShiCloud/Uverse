"""
PDF 解析进程池 - 使用子进程执行 MinerU 解析

核心设计：通过独立子进程执行 MinerU，可以强制终止，实现真正的取消功能。
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
from typing import Dict, Optional, Any, Callable
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
    """
    终止进程及其子进程树
    返回是否成功终止
    """
    if process.poll() is not None:
        # 进程已经结束
        return True
    
    try:
        if _IS_WINDOWS:
            # Windows: 使用 taskkill 终止进程树
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
                # 备用：直接 terminate
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
            # Unix/Linux/macOS: 使用进程组信号
            try:
                # 获取进程组 ID，终止整个进程组
                pgid = os.getpgid(process.pid)
                os.killpg(pgid, signal.SIGTERM)
                
                # 等待一段时间让进程优雅退出
                try:
                    process.wait(timeout=3)
                    return True
                except subprocess.TimeoutExpired:
                    pass
                
                # 如果还在运行，强制终止
                if process.poll() is None:
                    os.killpg(pgid, signal.SIGKILL)
                    process.wait(timeout=1)
                return True
            except ProcessLookupError:
                # 进程已经不存在
                return True
            except Exception as e:
                logger.error(f"[ProcessPool] 终止进程组失败: {e}")
                # 备用：直接 kill
                try:
                    process.kill()
                    return True
                except:
                    return False
    except Exception as e:
        logger.error(f"[ProcessPool] 终止进程时出错: {e}")
        return False


def stop_parse_process(task_id: str) -> bool:
    """
    强制停止解析进程
    
    Args:
        task_id: 任务 ID
        
    Returns:
        是否成功发送终止信号
    """
    logger.info(f"[ProcessPool] 尝试停止任务 {task_id}")
    
    # 设置取消信号（让子进程自己检测并优雅退出）
    _set_cancel_signal(task_id)
    
    # 强制终止进程
    with _process_lock:
        if task_id in _running_processes:
            process = _running_processes[task_id]
            logger.info(f"[ProcessPool] 终止进程 PID {process.pid}")
            success = _kill_process_tree(process)
            # 不立即从字典移除，让 parse_pdf_in_process 清理
            return success
    
    logger.info(f"[ProcessPool] 未找到运行中的进程 {task_id}")
    return False


def _get_worker_executable() -> Optional[Path]:
    """
    获取 PDF Worker 可执行文件路径（打包环境下使用独立的 worker 可执行文件）
    """
    if hasattr(sys, '_MEIPASS'):
        # 打包环境：查找 pdf-worker 可执行文件
        meipass = Path(sys._MEIPASS)
        
        # 在 macOS 上，目录结构是：
        # Uverse.app/Contents/Resources/backend/uverse-backend/_internal/
        # Uverse.app/Contents/Resources/backend/pdf-worker/
        # 所以 _MEIPASS 是 uverse-backend/_internal，需要向上两级再找 pdf-worker
        
        # 可能的 worker 路径（macOS 应用包结构）
        worker_paths = [
            # combined.spec 模式：pdf-worker 与 uverse-backend 同级
            # _MEIPASS = uverse-backend/_internal, parent = uverse-backend/
            meipass.parent / 'pdf-worker',
            # onedir 模式：与 uverse-backend 同级的 pdf-worker 目录
            meipass.parent.parent / 'pdf-worker' / 'pdf-worker',
            # 备用：在 _internal 内部
            meipass / 'pdf-worker' / 'pdf-worker',
            meipass / 'pdf-worker',
        ]
        
        # Windows 可执行文件扩展名
        if _IS_WINDOWS:
            worker_paths = [p.with_suffix('.exe') for p in worker_paths]
        
        for worker_path in worker_paths:
            if worker_path.exists():
                logger.info(f"[ProcessPool] 找到 PDF Worker: {worker_path}")
                return worker_path
        
        # 调试信息
        logger.warning(f"[ProcessPool] 未找到 pdf-worker，_MEIPASS={meipass}")
        logger.warning(f"[ProcessPool] 尝试过的路径: {[str(p) for p in worker_paths]}")
    return None


def _get_python_executable() -> str:
    """获取 Python 解释器路径（仅在无法使用独立 worker 时调用）"""
    # 检查是否在 PyInstaller 打包环境中
    if hasattr(sys, '_MEIPASS'):
        # 打包环境中 sys.executable 是打包后的二进制，不是 Python
        # 需要找到系统中的 Python 解释器
        import shutil
        
        # 优先尝试系统默认 Python 路径（避免使用开发环境虚拟环境）
        system_pythons = [
            '/usr/bin/python3',
            '/usr/local/bin/python3',
            '/opt/homebrew/bin/python3',  # macOS ARM64 Homebrew
            '/opt/local/bin/python3',     # MacPorts
        ]
        
        for python_path in system_pythons:
            if os.path.exists(python_path) and os.access(python_path, os.X_OK):
                logger.info(f"[ProcessPool] 打包模式，使用系统 Python: {python_path}")
                return python_path
        
        # 备用：尝试使用 PATH 中的 python3，但要过滤开发环境路径
        python_cmd = shutil.which('python3')
        if python_cmd:
            # 避免使用开发环境虚拟环境的 Python
            if '.venv' not in python_cmd and 'virtualenv' not in python_cmd:
                logger.info(f"[ProcessPool] 打包模式，使用 PATH Python: {python_cmd}")
                return python_cmd
            else:
                logger.warning(f"[ProcessPool] 找到的 Python 在虚拟环境中，尝试其他选项: {python_cmd}")
        
        # 最后尝试 python
        python_cmd = shutil.which('python')
        if python_cmd and '.venv' not in python_cmd:
            logger.info(f"[ProcessPool] 打包模式，使用 python: {python_cmd}")
            return python_cmd
        
        # 如果没有找到，返回 sys.executable 让调用者处理错误
        logger.error(f"[ProcessPool] 打包模式，未找到合适的系统 Python")
    return sys.executable


def _get_wrapper_script_path() -> Path:
    """获取 wrapper 脚本路径"""
    # 在开发环境中，使用相对于 backend 目录的路径
    # 实际的 wrapper 脚本是 workers/pdf_wrapper.py
    backend_dir = Path(__file__).parent.parent
    wrapper_path = backend_dir / "workers" / "pdf_wrapper.py"
    
    logger.info(f"[ProcessPool] 尝试开发环境路径: {wrapper_path} (exists={wrapper_path.exists()})")
    if wrapper_path.exists():
        return wrapper_path
    
    # 在 PyInstaller 打包环境中，使用 _MEIPASS
    if hasattr(sys, '_MEIPASS'):
        logger.info(f"[ProcessPool] PyInstaller 模式，_MEIPASS={sys._MEIPASS}")
        # PyInstaller onedir 模式下，数据文件在 _internal 目录
        wrapper_path = Path(sys._MEIPASS) / "workers" / "pdf_wrapper.py"
        logger.info(f"[ProcessPool] 尝试 _MEIPASS 路径: {wrapper_path} (exists={wrapper_path.exists()})")
        if wrapper_path.exists():
            return wrapper_path
        # 尝试 _internal 子目录
        wrapper_path = Path(sys._MEIPASS) / "_internal" / "workers" / "pdf_wrapper.py"
        logger.info(f"[ProcessPool] 尝试 _MEIPASS/_internal 路径: {wrapper_path} (exists={wrapper_path.exists()})")
        if wrapper_path.exists():
            return wrapper_path
        # 兼容旧的路径结构（如果打包时文件被放在根目录）
        wrapper_path = Path(sys._MEIPASS) / "pdf_wrapper.py"
        logger.info(f"[ProcessPool] 尝试 _MEIPASS 根目录: {wrapper_path} (exists={wrapper_path.exists()})")
        if wrapper_path.exists():
            return wrapper_path
    
    # 如果找不到，假设它在当前目录或 PYTHONPATH 中
    wrapper_path = Path("pdf_wrapper.py")
    logger.info(f"[ProcessPool] 尝试当前目录路径: {wrapper_path} (exists={wrapper_path.exists()})")
    if wrapper_path.exists():
        return wrapper_path
    
    # 最后尝试 _internal 子目录（相对路径）
    wrapper_path = Path("_internal") / "workers" / "pdf_wrapper.py"
    logger.info(f"[ProcessPool] 尝试相对 _internal 路径: {wrapper_path} (exists={wrapper_path.exists()})")
    if wrapper_path.exists():
        return wrapper_path
    
    logger.error(f"[ProcessPool] 找不到 pdf_wrapper.py")
    return wrapper_path  # 返回默认路径，让调用者处理不存在的情况


class LogInterceptor:
    """拦截子进程的日志输出"""
    
    def __init__(self, task_id: str, log_callback: Optional[Callable[[str, str], None]] = None):
        self.task_id = task_id
        self.log_callback = log_callback
        self._stopped = False
        self._thread: Optional[threading.Thread] = None
    
    def start_intercept(self, pipe):
        """开始拦截管道输出"""
        self._thread = threading.Thread(
            target=self._intercept_thread,
            args=(pipe,),
            daemon=True
        )
        self._thread.start()
    
    def _intercept_thread(self, pipe):
        """拦截线程 - 使用原始字节读取避免编码问题"""
        try:
            # 直接使用二进制管道（Popen 返回的 pipe 现在就是二进制模式）
            binary_pipe = pipe
            
            while not self._stopped:
                try:
                    # 直接读取字节
                    byte_line = binary_pipe.readline()
                    
                    if not byte_line:
                        break
                    
                    # 手动解码为 UTF-8
                    try:
                        line = byte_line.decode('utf-8')
                    except UnicodeDecodeError:
                        line = byte_line.decode('utf-8', errors='replace')
                    
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        # 尝试解析 JSON 日志
                        data = json.loads(line)
                        if data.get("type") == "log":
                            level = data.get("level", "INFO")
                            message = data.get("message", "")
                            if self.log_callback:
                                self.log_callback(level, message)
                            continue
                    except json.JSONDecodeError:
                        pass
                    
                    # 非 JSON 输出，直接记录
                    if self.log_callback:
                        self.log_callback("INFO", line)
                        
                except Exception as e:
                    if not self._stopped:
                        logger.debug(f"[ProcessPool] 日志拦截行处理异常: {e}")
                    break
        except Exception as e:
            if not self._stopped:
                logger.error(f"[ProcessPool] 日志拦截异常: {e}")
        finally:
            try:
                pipe.close()
            except:
                pass
    
    def stop(self):
        """停止拦截"""
        self._stopped = True
        if self._thread and self._thread.is_alive():
            # 等待线程结束，最多 2 秒
            self._thread.join(timeout=2)


async def parse_pdf_in_process(
    pdf_path: str,
    doc_id: str,
    task_id: str,
    output_dir: str,
    config_path: str,
    device: str = "cpu",
    backend: str = "pipeline"
) -> Dict[str, Any]:
    """
    使用子进程执行 PDF 解析
    
    优势：
    1. 可以完全终止进程（包括子进程树）
    2. 进程崩溃不会影响主服务
    3. 资源隔离更好
    """
    logger.info(f"[ProcessPool] 开始解析任务 {task_id} (子进程模式)")
    
    # 清理之前的取消信号
    _clear_cancel_signal(task_id)
    
    cancel_signal_path = _get_cancel_signal_path(task_id)
    
    # 优先尝试使用独立的 PDF Worker 可执行文件（打包环境）
    worker_exe = _get_worker_executable()
    
    if worker_exe:
        # 使用独立的 worker 可执行文件（打包环境）
        cmd = [
            str(worker_exe),
            "--pdf-path", pdf_path,
            "--output-dir", output_dir,
            "--config-path", config_path,
            "--doc-id", doc_id,
            "--device", device,
            "--cancel-check-file", str(cancel_signal_path),
        ]
        logger.info(f"[ProcessPool] 使用独立 PDF Worker: {worker_exe}")
        logger.info(f"[ProcessPool] 启动子进程: {cmd}")
        
        # 检查 worker 可执行文件
        if not worker_exe.exists():
            logger.error(f"[ProcessPool] PDF Worker 不存在: {worker_exe}")
            return {
                "success": False,
                "error": f"PDF 解析器启动失败: worker 可执行文件不存在",
            }
        
        # 设置工作目录为 worker 所在目录（某些依赖可能需要）
        cwd = str(worker_exe.parent)
    else:
        # 开发环境：使用 Python + wrapper 脚本
        python_exe = _get_python_executable()
        wrapper_script = _get_wrapper_script_path()
        
        cmd = [
            python_exe,
            str(wrapper_script),
            "--pdf-path", pdf_path,
            "--output-dir", output_dir,
            "--config-path", config_path,
            "--doc-id", doc_id,
            "--device", device,
            "--cancel-check-file", str(cancel_signal_path),
        ]
        
        logger.info(f"[ProcessPool] Python 解释器: {python_exe}")
        logger.info(f"[ProcessPool] Wrapper 脚本: {wrapper_script} (exists={wrapper_script.exists()})")
        logger.info(f"[ProcessPool] 启动子进程: {cmd}")
        
        # 检查 wrapper 脚本是否存在
        if not wrapper_script.exists():
            logger.error(f"[ProcessPool] Wrapper 脚本不存在: {wrapper_script}")
            return {
                "success": False,
                "error": f"PDF 解析器启动失败: wrapper 脚本不存在",
            }
        
        cwd = str(wrapper_script.parent) if wrapper_script.exists() else str(Path.cwd())
    
    # 设置日志回调
    log_callback = None
    try:
        from core.parse_logger import get_parse_logger
        from core.file_logger import get_file_log_manager
        parse_logger = get_parse_logger()
        file_log_manager = get_file_log_manager()
        
        def log_callback(level: str, message: str):
            # 1. 发送到 ParseLogger（内存，用于前端实时显示）
            parse_logger.add_log_sync(task_id, level, message)
            # 2. 直接写入日志文件（绕过 logging 配置不确定性）
            file_log_manager.add_log(
                level=level,
                message=f"[{task_id}] {message}",
                source="mineru"
            )
    except Exception as e:
        logger.warning(f"[ProcessPool] 无法设置日志回调: {e}")
        log_callback = None
    
    # 配置子进程启动参数
    startupinfo = None
    preexec_fn = None
    
    if _IS_WINDOWS:
        # Windows: 隐藏控制台窗口
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
    else:
        # Unix: 创建新进程组
        preexec_fn = os.setsid
    
    # 设置子进程环境变量，确保 UTF-8 编码
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    
    # 启动子进程（使用二进制模式避免 Windows 文本编码问题）
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,  # 二进制模式使用无缓冲
            text=False,  # 二进制模式
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
    
    # 启动日志拦截（只拦截 stderr）
    log_interceptor = LogInterceptor(task_id, log_callback)
    if process.stderr:
        log_interceptor.start_intercept(process.stderr)
    
    try:
        # 等待子进程完成或取消
        logger.info(f"[ProcessPool] 等待子进程 PID {process.pid} 完成...")
        
        # 创建异步任务来等待进程
        def wait_process():
            """在线程中等待进程，避免阻塞事件循环"""
            try:
                returncode = process.wait()
                # 只读取 stdout，stderr 由拦截器处理
                stdout_bytes = process.stdout.read() if process.stdout else b""
                # 解码为 UTF-8 字符串
                try:
                    stdout = stdout_bytes.decode('utf-8') if stdout_bytes else ""
                except UnicodeDecodeError:
                    stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ""
                return returncode, stdout
            except Exception as e:
                logger.error(f"[ProcessPool] wait_process 异常: {e}")
                return -1, ""
        
        loop = asyncio.get_event_loop()
        # 使用 run_in_executor 创建 Future，然后用 wrap_future 包装
        executor_future = loop.run_in_executor(None, wait_process)
        
        # 同时等待进程完成和检查取消
        cancelled_during_wait = False
        returncode = -1
        stdout = ""
        
        # 使用更简单的方式：检查进程状态并定期轮询
        check_interval = 0.5  # 每 0.5 秒检查一次
        while True:
            # 检查进程是否结束
            if process.poll() is not None:
                # 进程已结束，获取结果
                try:
                    returncode, stdout = await asyncio.wrap_future(executor_future)
                except Exception as e:
                    logger.error(f"[ProcessPool] 获取进程结果失败: {e}")
                    returncode, stdout = process.returncode, ""
                break
            
            # 检查是否被取消
            try:
                from routers.documents import check_cancelled
                if check_cancelled(task_id):
                    logger.info(f"[ProcessPool] 检测到取消请求，终止子进程 {process.pid}")
                    cancelled_during_wait = True
                    _kill_process_tree(process)
                    # 等待进程实际结束
                    try:
                        returncode, stdout = await asyncio.wait_for(
                            asyncio.wrap_future(executor_future), 
                            timeout=5.0
                        )
                    except asyncio.TimeoutError:
                        returncode, stdout = -1, ""
                    break
            except Exception as e:
                logger.debug(f"[ProcessPool] 检查取消状态时出错: {e}")
            
            # 等待一小段时间
            await asyncio.sleep(check_interval)
        
        # 停止日志拦截
        log_interceptor.stop()
        
        # 检查是否被取消（优先于 returncode 检查）
        if cancelled_during_wait or check_cancelled(task_id):
            return {
                "success": False,
                "error": "任务已被用户取消",
                "cancelled": True
            }
        
        # 检查取消信号文件（备用方式）
        if _get_cancel_signal_path(task_id).exists():
            return {
                "success": False,
                "error": "任务已被用户取消",
                "cancelled": True
            }
        
        # 检查返回码
        logger.info(f"[ProcessPool] 进程返回码: {returncode}")
        if returncode != 0:
            # 可能是被信号终止（如 SIGTERM=15, SIGKILL=9）
            if returncode < 0:
                signal_name = f"信号 {-returncode}"
                try:
                    signal_name = signal.Signals(-returncode).name
                except:
                    pass
                logger.warning(f"[ProcessPool] 进程被 {signal_name} 终止")
                
                # 如果取消标志已设置，视为正常取消
                if check_cancelled(task_id):
                    return {
                        "success": False,
                        "error": "任务已被用户取消",
                        "cancelled": True
                    }
            
            # 解析失败
            error_msg = f"解析进程失败 (exit code: {returncode})"
            logger.error(f"[ProcessPool] 解析失败，stdout 前500字符: {stdout[:500] if stdout else '空'}")
            
            try:
                # 尝试从 stdout 解析错误
                if stdout:
                    lines = stdout.strip().split('\n')
                    for line in reversed(lines):
                        line = line.strip()
                        if line:
                            try:
                                result = json.loads(line)
                                if isinstance(result, dict) and "error" in result:
                                    error_msg = result.get("error", error_msg)
                                    logger.info(f"[ProcessPool] 从 stdout 解析到错误: {error_msg}")
                                    break
                            except json.JSONDecodeError:
                                continue
            except Exception as e:
                logger.error(f"[ProcessPool] 解析错误信息失败: {e}")
            
            return {
                "success": False,
                "error": error_msg,
            }
        
        # 解析 stdout 获取结果
        logger.info(f"[ProcessPool] 解析 stdout，总长度: {len(stdout) if stdout else 0}")
        try:
            # 最后一行应该是 JSON 结果
            lines = stdout.strip().split('\n') if stdout else []
            logger.info(f"[ProcessPool] stdout 行数: {len(lines)}")
            
            for line in reversed(lines):
                line = line.strip()
                if line:
                    try:
                        result = json.loads(line)
                        if isinstance(result, dict) and "success" in result:
                            logger.info(f"[ProcessPool] 解析完成: success={result.get('success')}")
                            return result
                    except json.JSONDecodeError:
                        continue
            
            # 没有找到有效结果
            logger.error(f"[ProcessPool] 未找到有效 JSON 结果，stdout 最后500字符: {stdout[-500:] if stdout else '空'}")
            return {
                "success": False,
                "error": "无法解析子进程输出",
            }
            
        except Exception as e:
            logger.error(f"[ProcessPool] 解析结果失败: {e}")
            return {
                "success": False,
                "error": f"解析结果失败: {e}",
            }
            
    except asyncio.CancelledError:
        # 当前 asyncio 任务被取消（可能是 FastAPI 后台任务取消）
        logger.info(f"[ProcessPool] asyncio 任务被取消，终止子进程并返回取消结果")
        _kill_process_tree(process)
        # 返回取消结果而不是抛出异常，让调用方正常处理
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
        # 停止日志拦截
        log_interceptor.stop()
        
        # 从字典中移除
        with _process_lock:
            _running_processes.pop(task_id, None)
        
        # 清理取消信号
        _clear_cancel_signal(task_id)
        
        # 确保进程已终止
        if process.poll() is None:
            logger.warning(f"[ProcessPool] 进程 {process.pid} 仍未终止，强制杀死")
            _kill_process_tree(process)


def _check_cancelled(task_id: str) -> bool:
    """检查任务是否被取消（从 documents 模块导入）"""
    if task_id:
        try:
            from routers.documents import check_cancelled
            return check_cancelled(task_id)
        except:
            pass
    return False
