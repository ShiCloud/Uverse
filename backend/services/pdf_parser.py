"""
PDF 解析服务 - 使用 MinerU Python API
输出保存到 out 目录
"""
import os
import sys
import json
import io
from pathlib import Path
from typing import Dict, Optional, Callable

# 注意：多进程启动方法在 main.py 中统一设置，避免重复设置
# if hasattr(sys, '_MEIPASS'):
#     import multiprocessing
#     try:
#         multiprocessing.set_start_method('spawn', force=True)
#     except RuntimeError:
#         pass

# 在 PyInstaller 打包环境下，让 MinerU 认为当前是 Windows 环境，从而禁用多进程
# 这是避免 ProcessPoolExecutor 在打包环境下出问题的关键
if hasattr(sys, '_MEIPASS'):
    import mineru.utils.check_sys_env
    mineru.utils.check_sys_env.is_windows_environment = lambda: True
    print("[PDFParser] 打包模式：已禁用 MinerU 多进程渲染")

from loguru import logger

# 导入 MinerU 的解析函数
from mineru.cli.common import do_parse, read_fn


class LoguruInterceptor:
    """拦截 loguru 日志并传递给回调函数"""
    
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self.log_callback = log_callback
        self._handler_id = None
    
    def __call__(self, message):
        """接收 loguru 日志消息"""
        if self.log_callback:
            record = message.record
            level = record["level"].name
            msg = record["message"]
            self.log_callback(level, msg)
    
    def start(self):
        """开始拦截日志"""
        # 添加自定义 sink
        self._handler_id = logger.add(
            self,
            level="INFO",
            format="{message}",
            catch=False
        )
    
    def stop(self):
        """停止拦截日志"""
        if self._handler_id is not None:
            try:
                logger.remove(self._handler_id)
            except:
                pass
            self._handler_id = None
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class TqdmInterceptor(io.StringIO):
    """拦截 tqdm 进度条输出并传递给回调函数"""
    
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        super().__init__()
        self.log_callback = log_callback
        self._original_stderr = None
        self._buffer = ""
    
    def write(self, s: str) -> int:
        """拦截写入操作"""
        # tqdm 使用 \r 来刷新行，我们累加缓冲区直到遇到换行符
        self._buffer += s
        
        # 处理缓冲区中的完整行
        if '\n' in self._buffer or '\r' in self._buffer:
            # 按换行符分割
            lines = self._buffer.replace('\r', '\n').split('\n')
            # 保留最后一个不完整的行
            self._buffer = lines[-1]
            # 处理完整的行
            for line in lines[:-1]:
                self._process_line(line)
        
        return super().write(s)
    
    def _process_line(self, line: str):
        """处理单行输出"""
        stripped = line.strip()
        if stripped and self.log_callback:
            # 移除 ANSI 控制字符
            import re
            clean_msg = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', stripped)
            clean_msg = re.sub(r'\x1b\[\?\d+[lh]', '', clean_msg)  # 光标控制
            if clean_msg:
                self.log_callback("INFO", clean_msg)
    
    def start(self):
        """开始拦截 stderr"""
        self._original_stderr = sys.stderr
        sys.stderr = self
    
    def stop(self):
        """恢复原始 stderr"""
        # 处理缓冲区中剩余的内容
        if self._buffer.strip():
            self._process_line(self._buffer)
        
        if self._original_stderr is not None:
            sys.stderr = self._original_stderr
            self._original_stderr = None
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def get_mineru_config_path() -> str:
    """
    获取 MinerU 配置文件路径
    如果 MODELS_DIR 环境变量被设置，动态生成配置文件并返回临时路径
    否则返回默认的 mineru.json 路径
    """
    # 检测是否在 PyInstaller 打包环境中
    is_frozen = getattr(sys, 'frozen', False)
    
    if is_frozen:
        project_root = Path(sys.executable).parent
    else:
        project_root = Path(__file__).parent.parent.parent
    
    models_dir_env = os.getenv("MODELS_DIR")
    
    if not models_dir_env:
        # 使用默认配置
        return str(project_root / "backend/models/mineru.json")
    
    # 解析模型目录路径
    if os.path.isabs(models_dir_env):
        models_dir = Path(models_dir_env)
    else:
        # 相对路径，基于 backend 目录
        backend_dir = Path(__file__).parent.parent
        models_dir = backend_dir / models_dir_env
    
    # 构建模型子目录路径
    models_dir = models_dir.resolve()
    pipeline_model = models_dir / "OpenDataLab/PDF-Extract-Kit-1___0"
    vlm_model = models_dir / "OpenDataLab/MinerU2___5-2509-1___2B"
    
    # 动态生成配置
    config = {
        "bucket_info": {
            "bucket-name-1": ["ak", "sk", "endpoint"],
            "bucket-name-2": ["ak", "sk", "endpoint"]
        },
        "latex-delimiter-config": {
            "display": {"left": "$$", "right": "$$"},
            "inline": {"left": "$", "right": "$"}
        },
        "llm-aided-config": {
            "title_aided": {
                "api_key": "your_api_key",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen3-next-80b-a3b-instruct",
                "enable_thinking": False,
                "enable": False
            }
        },
        "models-dir": {
            "pipeline": str(pipeline_model),
            "vlm": str(vlm_model)
        },
        "config_version": "1.3.1"
    }
    
    # 写入临时配置文件
    config_dir = models_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    temp_config_path = config_dir / "mineru_runtime.json"
    
    with open(temp_config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    
    return str(temp_config_path)


def get_mineru_output_dir() -> Path:
    """获取 MinerU 输出目录 - 优先使用环境变量 MINERU_OUTPUT_DIR"""
    output_dir_env = os.getenv('MINERU_OUTPUT_DIR')
    if output_dir_env:
        return Path(output_dir_env)
    
    # 默认使用用户可写目录
    if os.name == 'nt':  # Windows
        base_dir = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif os.uname().sysname == 'Darwin':  # macOS
        base_dir = Path.home() / 'Library' / 'Application Support'
    else:  # Linux
        base_dir = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return base_dir / 'Uverse' / 'outputs'


class PDFParser:
    """PDF 解析器，使用 MinerU Python API"""
    
    def __init__(self, output_dir: str = None):
        if output_dir is None:
            output_dir = str(get_mineru_output_dir())
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def check_models_available() -> bool:
        """检查 AI 模型是否可用"""
        models_dir_env = os.getenv("MODELS_DIR", "models")
        if os.path.isabs(models_dir_env):
            models_dir = Path(models_dir_env)
        else:
            backend_dir = Path(__file__).parent.parent
            models_dir = backend_dir / models_dir_env
        
        opendatalab_path = models_dir / "OpenDataLab"
        return opendatalab_path.exists() and opendatalab_path.is_dir()
    
    def get_pdf_page_count(self, pdf_path: str) -> int:
        """获取 PDF 总页数"""
        import fitz
        with fitz.open(pdf_path) as doc:
            return len(doc)
    
    def parse_pdf(
        self, 
        pdf_path: str, 
        doc_id: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        log_callback: Optional[Callable[[str, str], None]] = None,
        device: str = "cpu",
        backend: str = "pipeline",
        process_holder: Optional[dict] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> Dict:
        """
        解析 PDF 文件
        
        Args:
            pdf_path: PDF 文件路径
            doc_id: 文档 ID
            progress_callback: 进度回调函数
            log_callback: 日志回调函数
            device: 设备模式
            backend: 解析后端
            process_holder: （已弃用）
            cancel_check: （已弃用）
        
        Returns:
            解析结果字典
        """
        # 检查 AI 模型是否可用
        if not self.check_models_available():
            raise Exception("AI 模型文件缺失 (models/OpenDataLab)，无法解析 PDF")
        
        pdf_path = Path(pdf_path).resolve()
        if not pdf_path.exists():
            raise Exception(f"PDF 文件不存在: {pdf_path}")
        
        # 创建输出目录
        doc_output_dir = self.output_dir / doc_id
        doc_output_dir.mkdir(parents=True, exist_ok=True)
        
        if log_callback:
            log_callback("INFO", f"输出目录: {doc_output_dir}")
        
        # 设置环境变量
        config_path = get_mineru_config_path()
        os.environ["MINERU_TOOLS_CONFIG_JSON"] = config_path
        
        # 设备模式
        env_device = os.environ.get("MINERU_DEVICE", device)
        if os.getenv('MINERU_DEVICE_MODE', None) is None:
            os.environ['MINERU_DEVICE_MODE'] = env_device
        
        # VRAM 限制
        vram_limit = os.environ.get("MINERU_VRAM")
        if vram_limit and os.getenv('MINERU_VIRTUAL_VRAM_SIZE', None) is None:
            os.environ['MINERU_VIRTUAL_VRAM_SIZE'] = vram_limit
        
        # 虚拟显存
        virtual_vram = os.environ.get("MINERU_VIRTUAL_VRAM_SIZE")
        if virtual_vram and os.getenv('MINERU_VIRTUAL_VRAM_SIZE', None) is None:
            os.environ['MINERU_VIRTUAL_VRAM_SIZE'] = virtual_vram
        
        # 模型来源
        if os.getenv('MINERU_MODEL_SOURCE', None) is None:
            os.environ['MINERU_MODEL_SOURCE'] = 'local'
        
        env_backend = os.environ.get("MINERU_BACKEND", backend)
        
        if log_callback:
            log_callback("INFO", f"MinerU 后端: {env_backend}")
            if env_backend == "pipeline":
                log_callback("INFO", f"MinerU 设备模式: {env_device}")
        
        if progress_callback:
            progress_callback(0, 100, "正在读取 PDF 文件...")
        
        # 读取 PDF 文件
        pdf_bytes = read_fn(pdf_path)
        pdf_file_name = pdf_path.stem
        
        if progress_callback:
            progress_callback(10, 100, "正在解析 PDF...")
        
        # 调用 MinerU 解析（使用日志拦截器捕获 loguru 和 tqdm 输出）
        log_interceptor = LoguruInterceptor(log_callback)
        tqdm_interceptor = TqdmInterceptor(log_callback)
        try:
            with log_interceptor, tqdm_interceptor:
                do_parse(
                    output_dir=str(doc_output_dir),
                    pdf_file_names=[pdf_file_name],
                    pdf_bytes_list=[pdf_bytes],
                    p_lang_list=["ch"],
                    backend=env_backend,
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
            raise Exception(f"MinerU 解析失败: {e}")
        
        if progress_callback:
            progress_callback(90, 100, "正在处理结果...")
        
        # 查找生成的 Markdown 文件
        md_file = self._find_markdown_output(doc_output_dir, pdf_file_name)
        
        if not md_file:
            raise Exception("未找到生成的 Markdown 文件")
        
        if log_callback:
            log_callback("INFO", f"找到 Markdown 文件: {md_file}")
        
        # 查找图片目录
        images_dir = self._find_images_dir(doc_output_dir, pdf_file_name)
        
        if images_dir and log_callback:
            log_callback("INFO", f"找到图片目录: {images_dir}")
        
        # 复制 Markdown 文件到输出目录根目录
        final_md_path = doc_output_dir / f"{doc_id}.md"
        content = self._read_markdown_content(md_file)
        
        with open(final_md_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        if log_callback:
            log_callback("INFO", "解析完成")
        
        if progress_callback:
            progress_callback(100, 100, "解析完成")
        
        return {
            "doc_id": doc_id,
            "total_pages": self.get_pdf_page_count(str(pdf_path)),
            "batches": 1,
            "output_dir": str(doc_output_dir),
            "markdown_file": str(final_md_path),
            "images_dir": str(images_dir) if images_dir else None,
            "content": content
        }
    
    def _find_markdown_output(self, output_dir: Path, pdf_file_name: str) -> Optional[Path]:
        """查找生成的 Markdown 文件"""
        # MinerU 生成的结构: {output_dir}/{filename}/{parse_method}/{filename}.md
        for method in ["auto", "txt", "ocr"]:
            md_path = output_dir / pdf_file_name / method / f"{pdf_file_name}.md"
            if md_path.exists():
                return md_path
        
        # 尝试任何子目录中的 Markdown
        md_files = list(output_dir.rglob("*.md"))
        if md_files:
            return md_files[0]
        
        return None
    
    def _find_images_dir(self, output_dir: Path, pdf_file_name: str) -> Optional[Path]:
        """查找生成的图片目录"""
        for method in ["auto", "txt", "ocr"]:
            img_dir = output_dir / pdf_file_name / method / "images"
            if img_dir.exists() and img_dir.is_dir():
                return img_dir
        
        return None
    
    def _read_markdown_content(self, md_path: Path) -> str:
        """读取 Markdown 文件内容"""
        try:
            with open(md_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content
        except Exception as e:
            print(f"[Error] 读取 Markdown 失败: {e}")
            return ""


# 全局解析器实例
_pdf_parser = None


def get_pdf_parser() -> PDFParser:
    """获取 PDF 解析器实例"""
    global _pdf_parser
    if _pdf_parser is None:
        _pdf_parser = PDFParser()
    return _pdf_parser
