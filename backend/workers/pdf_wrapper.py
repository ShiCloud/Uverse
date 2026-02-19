#!/usr/bin/env python3
"""
PDF 解析 CLI Wrapper - 独立进程入口
被主进程通过 subprocess 调用，便于强制终止
"""
import sys

# 首先检查是否是 resource_tracker 的空参数调用
# 必须在导入其他模块之前退出，避免不必要的初始化
if len(sys.argv) == 1:
    sys.exit(0)
import os
import json
import argparse
import traceback
import io
import re
from pathlib import Path
from typing import Optional, Callable

# 保存原始 stderr 引用，确保日志输出不受拦截器影响
_original_stderr = sys.stderr

def log_json(level: str, message: str):
    """输出 JSON 格式日志到原始 stderr，主进程可以捕获"""
    log_entry = {
        "type": "log",
        "level": level,
        "message": message
    }
    # 使用原始 stderr，不受 TqdmInterceptor 影响
    print(json.dumps(log_entry, ensure_ascii=False), file=_original_stderr, flush=True)


class LoguruInterceptor:
    """拦截 loguru 日志并转换为 JSON 输出"""
    
    def __init__(self):
        self._handler_id = None
    
    def __call__(self, message):
        """接收 loguru 日志消息"""
        try:
            record = message.record
            level = record["level"].name
            msg = record["message"]
            log_json(level, msg)
        except Exception:
            pass
    
    def start(self):
        """开始拦截日志"""
        try:
            from loguru import logger as loguru_logger
            self._handler_id = loguru_logger.add(
                self,
                level="INFO",
                format="{message}",
                catch=False
            )
        except ImportError:
            pass
    
    def stop(self):
        """停止拦截日志"""
        if self._handler_id is not None:
            try:
                from loguru import logger as loguru_logger
                loguru_logger.remove(self._handler_id)
            except:
                pass
            self._handler_id = None
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class TqdmInterceptor(io.StringIO):
    """拦截 tqdm 进度条输出并转换为 JSON 日志"""
    
    def __init__(self):
        super().__init__()
        self._saved_stderr = None
        self._buffer = ""
    
    def write(self, s: str) -> int:
        """拦截写入操作"""
        self._buffer += s
        
        if '\n' in self._buffer or '\r' in self._buffer:
            lines = self._buffer.replace('\r', '\n').split('\n')
            self._buffer = lines[-1]
            for line in lines[:-1]:
                self._process_line(line)
        
        return super().write(s)
    
    def _process_line(self, line: str):
        """处理单行输出"""
        stripped = line.strip()
        if stripped:
            # 移除 ANSI 控制字符
            clean_msg = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', stripped)
            clean_msg = re.sub(r'\x1b\[\?\d+[lh]', '', clean_msg)
            if clean_msg:
                log_json("INFO", clean_msg)
    
    def start(self):
        """开始拦截 stderr"""
        self._saved_stderr = sys.stderr
        sys.stderr = self
    
    def stop(self):
        """恢复原始 stderr"""
        if self._buffer.strip():
            self._process_line(self._buffer)
        
        if self._saved_stderr is not None:
            sys.stderr = self._saved_stderr
            self._saved_stderr = None
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

def output_result(result: dict):
    """输出最终结果到 stdout"""
    print(json.dumps(result, ensure_ascii=False), flush=True)

class SilentArgumentParser(argparse.ArgumentParser):
    """静默参数解析器 - 遇到错误时不打印帮助信息"""
    def error(self, message):
        # 检查是否是 resource_tracker 的调用
        import json
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
    parser.add_argument('--device', default='cpu', help='设备模式')
    parser.add_argument('--cancel-check-file', help='取消检查文件路径（如果此文件存在则表示取消）')
    
    args = parser.parse_args()
    
    log_json("INFO", f"PDF CLI Wrapper 启动，文档 ID: {args.doc_id}")
    log_json("INFO", f"PDF 路径: {args.pdf_path}")
    log_json("INFO", f"输出目录: {args.output_dir}")
    
    # 检查文件是否存在
    if not os.path.exists(args.pdf_path):
        output_result({
            "success": False,
            "error": f"PDF 文件不存在: {args.pdf_path}"
        })
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
        log_json("INFO", "正在导入 MinerU...")
        from mineru.cli.common import do_parse, read_fn
        
        # 创建输出目录
        doc_output_dir = Path(args.output_dir)
        doc_output_dir.mkdir(parents=True, exist_ok=True)
        
        # 读取 PDF
        log_json("INFO", "读取 PDF 文件...")
        pdf_bytes = read_fn(args.pdf_path)
        pdf_file_name = Path(args.pdf_path).stem
        log_json("INFO", f"PDF 大小: {len(pdf_bytes)} bytes")
        
        # 定义取消检查函数
        def check_cancelled():
            if args.cancel_check_file and os.path.exists(args.cancel_check_file):
                return True
            return False
        
        # 检查是否已取消
        if check_cancelled():
            log_json("WARNING", "任务在开始执行前被取消")
            output_result({
                "success": False,
                "error": "任务已被用户取消",
                "cancelled": True
            })
            return 0
        
        # 执行解析
        log_json("INFO", "开始 PDF 解析...")
        
        # 使用日志拦截器捕获 MinerU 的日志
        log_interceptor = LoguruInterceptor()
        tqdm_interceptor = TqdmInterceptor()
        
        try:
            with log_interceptor, tqdm_interceptor:
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
        except Exception as e:
            log_json("ERROR", f"do_parse 异常: {e}")
            raise
        
        # 检查是否被取消（解析完成后）
        if check_cancelled():
            log_json("WARNING", "解析完成后检测到取消请求")
            output_result({
                "success": False,
                "error": "任务已被用户取消",
                "cancelled": True
            })
            return 0
        
        log_json("INFO", "PDF 解析完成")
        
        # 查找生成的 Markdown 文件
        md_file = None
        for f in doc_output_dir.rglob("*.md"):
            md_file = str(f)
            break
        
        # 查找图片目录
        images_dir = None
        for subdir in doc_output_dir.rglob("images"):
            if subdir.is_dir():
                images_dir = str(subdir)
                break
        
        # 复制 Markdown 到根目录
        final_md_path = doc_output_dir / f"{args.doc_id}.md"
        if md_file and Path(md_file).exists():
            import shutil
            shutil.copy2(md_file, final_md_path)
            log_json("INFO", f"已复制 Markdown 到: {final_md_path}")
        
        output_result({
            "success": True,
            "output_dir": str(doc_output_dir),
            "markdown_file": str(final_md_path) if final_md_path.exists() else md_file,
            "images_dir": images_dir,
        })
        return 0
        
    except Exception as e:
        error_trace = traceback.format_exc()
        log_json("ERROR", f"解析失败: {e}")
        log_json("ERROR", f"错误堆栈: {error_trace}")
        output_result({
            "success": False,
            "error": str(e),
            "traceback": error_trace
        })
        return 1

if __name__ == "__main__":
    sys.exit(main())
