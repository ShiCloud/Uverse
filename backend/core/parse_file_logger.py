"""
简化的解析日志管理器 - 直接写入文件，按 task 分文件存储
"""
import os
import sys
import json
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: str
    level: str
    message: str


def _get_log_dir(log_dir_name: str = "logs") -> Path:
    """获取日志目录路径 - 与 FileLogManager 保持一致
    
    开发模式：使用项目目录的 backend/logs
    打包模式：使用用户可写目录 (support/userData)
    """
    # 开发环境：使用项目目录
    if not getattr(sys, 'frozen', False):
        return Path(__file__).parent.parent / log_dir_name
    
    # 打包环境：使用用户可写目录 (与 FileLogManager 一致)
    if os.name == 'nt':  # Windows
        base_dir = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif sys.platform == 'darwin':  # macOS
        base_dir = Path.home() / 'Library' / 'Application Support'
    else:  # Linux
        base_dir = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    
    return base_dir / 'Uverse' / log_dir_name


class ParseFileLogger:
    """
    简化的解析日志管理器
    - 每个 task 一个日志文件: logs/parse/{task_id}.log
    - 批量写入，减少IO操作
    - 前端通过 API 轮询读取
    """
    
    def __init__(self, log_dir: str = None):
        # 自动推导日志目录（兼容打包模式）
        if log_dir is None:
            # 使用与 FileLogManager 相同的逻辑
            self.log_dir = _get_log_dir("logs") / "parse"
        else:
            self.log_dir = Path(log_dir)
        
        # 确保目录存在
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # 如果无法创建目录（如只读文件系统），使用临时目录
            import tempfile
            self.log_dir = Path(tempfile.gettempdir()) / "uverse" / "logs" / "parse"
            self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self._lock = threading.Lock()  # 线程安全
        self._buffers: Dict[str, List[Dict]] = {}  # 任务日志缓冲区
        self._buffer_size = 10  # 批量写入阈值
        self._flush_interval = 0.5  # 强制刷新间隔（秒）
        self._last_flush: Dict[str, float] = {}  # 上次刷新时间
        
        # 启动后台刷新线程
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()
    
    def _get_log_file(self, task_id: str) -> Path:
        """获取任务日志文件路径"""
        return self.log_dir / f"{task_id}.log"
    
    def create_task_logger(self, task_id: str):
        """创建任务日志记录器（兼容性方法，实际不需要创建）"""
        # 确保日志目录存在
        self.log_dir.mkdir(parents=True, exist_ok=True)
        # 清除旧日志（如果存在）
        self.clear_logs(task_id)
    
    def set_event_loop(self, loop):
        """设置事件循环（兼容性方法，文件日志不需要）"""
        pass  # 文件日志不需要事件循环
    
    def _flush_loop(self):
        """后台刷新线程 - 定期刷新缓冲区"""
        while True:
            time.sleep(self._flush_interval)
            try:
                self._flush_all_buffers()
            except Exception:
                pass
    
    def _flush_all_buffers(self):
        """刷新所有缓冲区"""
        with self._lock:
            current_time = time.time()
            for task_id, buffer in list(self._buffers.items()):
                last_flush = self._last_flush.get(task_id, 0)
                # 缓冲区有数据且超过刷新间隔，或者缓冲区已满
                if buffer and (current_time - last_flush > self._flush_interval or len(buffer) >= self._buffer_size):
                    self._write_buffer_to_file(task_id, buffer)
                    self._buffers[task_id] = []
                    self._last_flush[task_id] = current_time
    
    def _write_buffer_to_file(self, task_id: str, buffer: List[Dict]):
        """将缓冲区写入文件"""
        try:
            log_file = self._get_log_file(task_id)
            # 使用 'a' 模式一次性写入多条日志
            lines = [json.dumps(entry, ensure_ascii=False) + '\n' for entry in buffer]
            with open(log_file, 'a', encoding='utf-8', buffering=8192) as f:
                f.writelines(lines)
        except Exception as e:
            # 写入失败时打印错误但不抛出
            print(f"[ParseFileLogger] 写入日志失败: {e}")
    
    def flush_task_buffer(self, task_id: str):
        """强制刷新指定任务的缓冲区"""
        with self._lock:
            if task_id in self._buffers and self._buffers[task_id]:
                self._write_buffer_to_file(task_id, self._buffers[task_id])
                self._buffers[task_id] = []
                self._last_flush[task_id] = time.time()
    
    def add_log(self, task_id: str, level: str, message: str):
        """添加日志到文件（批量写入）"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # JSON Lines 格式
        log_entry = {
            "timestamp": timestamp,
            "level": level.upper(),
            "message": message
        }
        
        with self._lock:
            # 初始化缓冲区
            if task_id not in self._buffers:
                self._buffers[task_id] = []
                self._last_flush[task_id] = time.time()
            
            # 添加到缓冲区
            self._buffers[task_id].append(log_entry)
            
            # 如果缓冲区达到阈值，立即写入
            if len(self._buffers[task_id]) >= self._buffer_size:
                self._write_buffer_to_file(task_id, self._buffers[task_id])
                self._buffers[task_id] = []
                self._last_flush[task_id] = time.time()
    
    def get_log_stats(self, task_id: str) -> dict:
        """获取日志文件统计信息"""
        log_file = self._get_log_file(task_id)
        
        total_lines = 0
        total_size = 0
        
        if log_file.exists():
            try:
                stat = log_file.stat()
                total_size = stat.st_size
                with open(log_file, 'rb') as f:
                    for _ in f:
                        total_lines += 1
            except Exception:
                pass
        
        return {"exists": total_lines > 0, "size": total_size, "lines": total_lines}
    
    def get_logs(self, task_id: str, limit: int = 1000) -> List[LogEntry]:
        """读取日志文件和缓冲区"""
        log_file = self._get_log_file(task_id)
        
        all_logs = []
        
        # 1. 先从文件读取
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            all_logs.append(LogEntry(
                                timestamp=data.get("timestamp", ""),
                                level=data.get("level", "INFO"),
                                message=data.get("message", "")
                            ))
                        except json.JSONDecodeError:
                            continue
            except Exception:
                pass
        
        # 2. 从缓冲区读取未写入文件的日志（重要：包括错误日志）
        with self._lock:
            if task_id in self._buffers:
                for entry in self._buffers[task_id]:
                    all_logs.append(LogEntry(
                        timestamp=entry.get("timestamp", ""),
                        level=entry.get("level", "INFO"),
                        message=entry.get("message", "")
                    ))
        
        # 按时间戳排序
        all_logs.sort(key=lambda x: x.timestamp)
        
        # 返回最新的 limit 条
        if len(all_logs) > limit:
            all_logs = all_logs[-limit:]
        
        return all_logs
    
    def clear_logs(self, task_id: str):
        """清空日志文件"""
        with self._lock:
            # 先清空缓冲区
            if task_id in self._buffers:
                self._buffers[task_id] = []
            
            # 删除日志文件
            log_file = self._get_log_file(task_id)
            if log_file.exists():
                try:
                    log_file.unlink()
                except Exception:
                    pass
    
    def cleanup_old_logs(self, max_age_hours: int = 24):
        """清理旧的日志文件"""
        cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
        for log_file in self.log_dir.glob("*.log"):
            try:
                if log_file.stat().st_mtime < cutoff:
                    log_file.unlink()
            except Exception:
                pass


# 全局实例
_parse_file_logger = None


def get_parse_file_logger() -> ParseFileLogger:
    """获取全局实例"""
    global _parse_file_logger
    if _parse_file_logger is None:
        _parse_file_logger = ParseFileLogger()
    return _parse_file_logger
