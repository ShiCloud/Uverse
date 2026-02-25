#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF 解析 CLI Wrapper - 独立进程入口
被主进程通过 subprocess 调用，便于强制终止
"""
import sys
import os

# 设置 Python 使用 UTF-8 编码（必须在导入其他模块前设置）
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'

# 重新配置 stdout/stderr 编码（Windows 打包模式需要）
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

# 首先检查是否是 resource_tracker 的空参数调用
if len(sys.argv) == 1:
    sys.exit(0)

import json
import argparse
import traceback
import re
from pathlib import Path
from datetime import datetime

# 日志文件路径（由主进程传入）
LOG_FILE = None


def init_logger(log_file_path: str):
    """初始化日志文件"""
    global LOG_FILE
    LOG_FILE = log_file_path
    
    # 确保目录存在
    Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)


def log(level: str, message: str):
    """写入日志到文件
    
    Args:
        level: 日志级别
        message: 日志消息
    """
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    log_entry = {
        "timestamp": timestamp,
        "level": level.upper(),
        "message": message
    }
    
    # 写入日志文件
    if LOG_FILE:
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        except Exception:
            pass
    
    # 输出到 stdout（用于进程间通信，让主进程可以实时看到日志）
    try:
        print(f"[{level}] {message}", flush=True)
    except UnicodeEncodeError:
        print(f"[{level}] {message.encode('utf-8', errors='replace').decode('utf-8')}", flush=True)


class LoguruInterceptor:
    """
    拦截 loguru 日志（MinerU 使用）
    
    重要：这个拦截器会完全接管 loguru 的输出，移除默认的 stderr 输出，
    防止日志被重复捕获。
    """
    
    def __init__(self, log_func):
        self.log_func = log_func
        self._handler_id = None
        self._original_handlers = []
    
    def __call__(self, message):
        """接收 loguru 日志消息"""
        try:
            record = message.record
            level = record["level"].name
            msg = record["message"]
            # 标记为 MinerU 日志
            self.log_func(level, msg)
        except Exception:
            pass
    
    def start(self):
        """开始拦截 - 移除所有默认 handler，只保留我们的 interceptor"""
        try:
            from loguru import logger as loguru_logger
            
            # 保存当前的 handlers 配置（用于恢复）
            self._original_handlers = list(loguru_logger._core.handlers.values())
            
            # 移除所有现有的 handler（包括默认的 stderr 输出）
            loguru_logger.remove()
            
            # 添加我们的 interceptor 作为唯一的 handler
            self._handler_id = loguru_logger.add(
                self,
                level="DEBUG",  # 捕获所有级别的日志
                format="{message}",  # 简化格式，只保留消息内容
                catch=False
            )
        except ImportError:
            pass
    
    def stop(self):
        """停止拦截 - 恢复原来的配置"""
        if self._handler_id is not None:
            try:
                from loguru import logger as loguru_logger
                loguru_logger.remove(self._handler_id)
                self._handler_id = None
                
                # 恢复原来的 handlers
                for handler in self._original_handlers:
                    try:
                        loguru_logger.add(handler)
                    except:
                        pass
            except:
                pass
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class TqdmInterceptor:
    """
    拦截 tqdm 进度条输出（MinerU 使用）
    
    注意：由于 LoguruInterceptor 已经移除了 loguru 的 stderr 输出，
    这里只捕获真正的 tqdm 进度条输出。
    """
    
    def __init__(self, log_func):
        self.log_func = log_func
        self._original_stderr = None
        self._buffer = ""
        self._last_msg = ""
        self._ansi_re = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
        self._progress_pattern = re.compile(r'(\d+%).*?(\d+/\d+)')
    
    def write(self, s):
        """拦截写入操作"""
        # 处理字节
        if isinstance(s, bytes):
            try:
                s = s.decode('utf-8')
            except:
                s = s.decode('utf-8', errors='replace')
        
        # 移除 ANSI 控制字符
        s = self._ansi_re.sub('', s)
        
        # 累积到缓冲区
        self._buffer += s
        
        # 处理换行或回车（tqdm 使用 \r 更新同一行）
        if '\n' in s:
            lines = self._buffer.split('\n')
            self._buffer = lines[-1]
            for line in lines[:-1]:
                self._process_line(line)
        elif '\r' in s:
            parts = self._buffer.rsplit('\r', 1)
            if len(parts) == 2:
                if parts[0] and '\n' in parts[0]:
                    lines = parts[0].split('\n')
                    for line in lines[:-1]:
                        self._process_line(line)
                self._buffer = parts[1]
                self._process_progress(parts[1])
        
        return len(s)
    
    def _process_progress(self, line: str):
        """处理进度条行 - 只提取关键进度信息"""
        line = line.strip()
        if not line:
            return
        
        # 只处理包含百分比的进度条
        if '%' not in line:
            return
        
        # 简化进度信息：提取 "XX% X/X [elapsed<remaining]" 格式
        match = self._progress_pattern.search(line)
        if match:
            # 清理多余的空格
            progress_msg = ' '.join(line.split())
            if progress_msg and progress_msg != self._last_msg:
                self._last_msg = progress_msg
                self.log_func("INFO", progress_msg)
    
    def _process_line(self, line: str):
        """处理普通行 - 忽略 loguru 格式的日志"""
        line = line.strip()
        if not line:
            return
        
        # 跳过 loguru 格式的日志（时间戳开头）
        if re.match(r'^\[\d{2}:\d{2}:\d{2}\.\d+\]', line):
            return
        
        # 跳过日志级别标签的行（已经被 loguru 处理过的）
        if re.match(r'^\[(INFO|WARNING|ERROR|DEBUG)\]', line):
            return
        
        # 跳过 tqdm 的进度条行（已经在 _process_progress 中处理）
        if '%' in line and self._progress_pattern.search(line):
            return
        
        if line and line != self._last_msg:
            self._last_msg = line
            self.log_func("INFO", line)
    
    def flush(self):
        """刷新缓冲区"""
        if self._buffer.strip():
            self._process_line(self._buffer)
            self._buffer = ""
    
    def isatty(self):
        """模拟 tty"""
        return False
    
    def start(self):
        """开始拦截 stderr"""
        self._original_stderr = sys.stderr
        sys.stderr = self
    
    def stop(self):
        """恢复原始 stderr"""
        self.flush()
        if self._original_stderr is not None:
            sys.stderr = self._original_stderr
            self._original_stderr = None
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class SilentArgumentParser(argparse.ArgumentParser):
    """静默参数解析器"""
    def error(self, message):
        result = {
            "success": False,
            "error": f"参数错误: {message}",
            "traceback": ""
        }
        print(json.dumps(result, ensure_ascii=False), flush=True)
        sys.exit(1)


def main():
    parser = SilentArgumentParser(description='PDF 解析 CLI Wrapper')
    parser.add_argument('--pdf-path', required=True, help='PDF 文件路径')
    parser.add_argument('--output-dir', required=True, help='输出目录')
    parser.add_argument('--config-path', required=True, help='MinerU 配置文件路径')
    parser.add_argument('--doc-id', required=True, help='文档 ID')
    parser.add_argument('--task-id', required=True, help='任务 ID')
    parser.add_argument('--log-file', required=True, help='日志文件路径')
    parser.add_argument('--filename', help='原始文件名')
    parser.add_argument('--device', default='cpu', help='设备模式')
    parser.add_argument('--cancel-check-file', help='取消检查文件路径')
    
    args = parser.parse_args()
    
    # 初始化日志
    init_logger(args.log_file)
    
    log("INFO", f"PDF 路径: {args.pdf_path}")
    log("INFO", f"输出目录: {args.output_dir}")
    
    # 转换为绝对路径
    pdf_path = Path(args.pdf_path).resolve()
    output_dir = Path(args.output_dir).resolve()
    
    # 检查文件是否存在
    if not pdf_path.exists():
        log("ERROR", f"PDF 文件不存在: {pdf_path}")
        print(json.dumps({
            "success": False,
            "error": f"PDF 文件不存在: {pdf_path}"
        }, ensure_ascii=False), flush=True)
        return 1
    
    try:
        # 设置环境变量
        os.environ["MINERU_TOOLS_CONFIG_JSON"] = args.config_path
        os.environ['MINERU_DEVICE_MODE'] = args.device
        os.environ['MINERU_MODEL_SOURCE'] = 'local'
        os.environ["MINERU_PDF_RENDER_THREADS"] = "1"
        
        # 打包环境下禁用多进程
        if os.environ.get('UVERSE_PACKAGED') or hasattr(sys, '_MEIPASS'):
            try:
                import mineru.utils.check_sys_env
                mineru.utils.check_sys_env.is_windows_environment = lambda: True
            except:
                pass
        
        # 导入 MinerU
        log("INFO", "正在加载 MinerU...")
        from mineru.cli.common import do_parse, read_fn
        
        # 创建输出目录
        doc_output_dir = output_dir / args.doc_id
        doc_output_dir.mkdir(parents=True, exist_ok=True)
        
        # 读取 PDF
        log("INFO", "读取 PDF 文件...")
        pdf_bytes = read_fn(str(pdf_path))
        pdf_file_name = pdf_path.stem
        log("INFO", f"PDF 大小: {len(pdf_bytes)} bytes")
        
        # 获取 PDF 页数
        try:
            import fitz
            pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_pages = len(pdf_doc)
            pdf_doc.close()
            log("INFO", f"PDF 页数: {total_pages}")
        except Exception as e:
            log("WARNING", f"无法获取 PDF 页数: {e}")
            total_pages = 1
        
        # 检查是否已取消
        if args.cancel_check_file and os.path.exists(args.cancel_check_file):
            log("WARNING", "任务在开始执行前被取消")
            print(json.dumps({
                "success": False,
                "error": "任务已被用户取消",
                "cancelled": True
            }, ensure_ascii=False), flush=True)
            return 0
        
        # 执行解析
        # 使用拦截器捕获 MinerU 的日志和进度条
        # LoguruInterceptor 会先移除 loguru 的默认 stderr 输出，防止重复
        with LoguruInterceptor(log), TqdmInterceptor(log):
            do_parse(
                output_dir=str(doc_output_dir),
                pdf_file_names=[pdf_file_name],
                pdf_bytes_list=[pdf_bytes],
                p_lang_list=["ch"],
                backend="pipeline",
                parse_method="auto",
                formula_enable=True,
                table_enable=True,
                f_draw_layout_bbox=False,
                f_draw_span_bbox=False,
                f_dump_md=True,
                f_dump_middle_json=False,
                f_dump_model_output=False,
                f_dump_orig_pdf=False,
                f_dump_content_list=False,
            )
        
        # 检查是否被取消
        if args.cancel_check_file and os.path.exists(args.cancel_check_file):
            log("WARNING", "解析完成后检测到取消请求")
            print(json.dumps({
                "success": False,
                "error": "任务已被用户取消",
                "cancelled": True
            }, ensure_ascii=False), flush=True)
            return 0
        
        # 查找生成的 Markdown 文件
        md_files = list(doc_output_dir.rglob("*.md"))
        md_file = str(md_files[0]) if md_files else None
        if md_file:
            log("INFO", f"找到 Markdown 文件: {md_file}")
        
        # 查找图片目录
        images_dirs = [d for d in doc_output_dir.rglob("images") if d.is_dir()]
        images_dir = str(images_dirs[0]) if images_dirs else None
        
        # 复制 Markdown 到根目录
        final_md_path = doc_output_dir / f"{args.doc_id}.md"
        
        if md_file and os.path.exists(md_file):
            import shutil
            shutil.copyfile(md_file, str(final_md_path))
            log("INFO", f"已复制 Markdown 到: {final_md_path}")
        
        # 输出结果到 stdout
        result = {
            "success": True,
            "output_dir": str(doc_output_dir),
            "markdown_file": str(final_md_path) if final_md_path.exists() else md_file,
            "images_dir": images_dir,
            "total_pages": total_pages,
            "batches": 1,
        }
        print(json.dumps(result, ensure_ascii=False), flush=True)
        log("INFO", "任务完成")
        return 0
        
    except Exception as e:
        error_trace = traceback.format_exc()
        log("ERROR", f"解析失败: {e}")
        print(json.dumps({
            "success": False,
            "error": str(e),
            "traceback": error_trace
        }, ensure_ascii=False), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
