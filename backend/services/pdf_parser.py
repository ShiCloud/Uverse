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
    """
    拦截 loguru 日志并传递给回调函数
    
    重要：这个拦截器会完全接管 loguru 的输出，移除默认的 stderr 输出，
    防止日志被重复捕获。
    """
    
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self.log_callback = log_callback
        self._handler_id = None
        self._original_handlers = []
    
    def __call__(self, message):
        """接收 loguru 日志消息"""
        if self.log_callback:
            record = message.record
            level = record["level"].name
            msg = record["message"]
            self.log_callback(level, msg)
    
    def start(self):
        """开始拦截 - 移除所有默认 handler，只保留我们的 interceptor"""
        # 保存当前的 handlers 配置（用于恢复）
        self._original_handlers = list(logger._core.handlers.values())
        
        # 移除所有现有的 handler（包括默认的 stderr 输出）
        logger.remove()
        
        # 添加我们的 interceptor 作为唯一的 handler
        self._handler_id = logger.add(
            self,
            level="DEBUG",
            format="{message}",
            catch=False
        )
    
    def stop(self):
        """停止拦截 - 恢复原来的配置"""
        if self._handler_id is not None:
            logger.remove(self._handler_id)
            self._handler_id = None
            
            # 恢复原来的 handlers
            for handler in self._original_handlers:
                try:
                    logger.add(handler)
                except:
                    pass
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class TqdmInterceptor(io.TextIOBase):
    """
    拦截 tqdm 进度条输出
    
    注意：由于 LoguruInterceptor 已经移除了 loguru 的 stderr 输出，
    这里只捕获真正的 tqdm 进度条输出。
    """
    
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        super().__init__()
        self.log_callback = log_callback
        self._original_stderr = None
        self._buffer = ""
        self._last_progress = ""
    
    def write(self, s) -> int:
        """拦截写入操作 - 处理字符串或字节"""
        # 处理字节输入
        if isinstance(s, bytes):
            try:
                s = s.decode('utf-8')
            except:
                s = s.decode('utf-8', errors='replace')
        
        # 移除 ANSI 控制字符
        import re
        s = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', s)
        
        # 累加缓冲区
        self._buffer += s
        
        # 处理缓冲区中的进度信息
        if '\r' in self._buffer:
            parts = self._buffer.rsplit('\r', 1)
            self._buffer = parts[-1]
            if parts[0]:
                self._process_progress(parts[0])
        
        return len(s)
    
    def flush(self):
        pass
    
    def _process_progress(self, text: str):
        """处理进度条文本 - 只提取进度信息"""
        if not self.log_callback:
            return
        
        # 清理并提取进度行
        lines = text.replace('\r', '\n').split('\n')
        for line in lines:
            line = line.strip()
            # 只处理包含百分比的进度条行
            if '%' in line and 'it/s' in line:
                # 简化进度信息
                clean_line = ' '.join(line.split())
                if clean_line and clean_line != self._last_progress:
                    self._last_progress = clean_line
                    self.log_callback("INFO", clean_line)
    
    def start(self):
        """开始拦截 stderr"""
        self._original_stderr = sys.stderr
        sys.stderr = self
    
    def stop(self):
        """恢复原始 stderr"""
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
    如果 MODELS_DIR 环境变量被设置且模型目录存在，更新 mineru.json 中的路径
    返回 mineru.json 的路径
    """
    # 检测是否在 PyInstaller 打包环境中
    is_frozen = getattr(sys, 'frozen', False)
    
    if is_frozen:
        # 打包环境下，exe 直接在 resources/backend/ 目录
        # mineru.json 在 resources/backend/models/ 目录
        backend_dir = Path(sys.executable).parent  # backend/
        default_config_path = backend_dir / "models" / "mineru.json"
    else:
        project_root = Path(__file__).parent.parent.parent
        default_config_path = project_root / "backend/models/mineru.json"
    
    models_dir_env = os.getenv("MODELS_DIR")
    
    if not models_dir_env:
        # 使用默认配置
        return str(default_config_path)
    
    # 解析模型目录路径
    if os.path.isabs(models_dir_env):
        models_dir = Path(models_dir_env)
    else:
        # 相对路径，基于 backend 目录
        backend_dir = Path(__file__).parent.parent
        models_dir = backend_dir / models_dir_env
    
    models_dir = models_dir.resolve()
    
    # 检查模型目录是否存在
    opendatalab_path = models_dir / "OpenDataLab"
    if not opendatalab_path.exists():
        print(f"[WARN] 模型目录不存在: {opendatalab_path}，使用默认配置")
        return str(default_config_path)
    
    # 构建模型子目录的绝对路径
    pipeline_model = models_dir / "OpenDataLab/PDF-Extract-Kit-1___0"
    vlm_model = models_dir / "OpenDataLab/MinerU2___5-2509-1___2B"
    
    # 检查具体的模型子目录是否存在
    if not pipeline_model.exists():
        print(f"[WARN] Pipeline 模型不存在: {pipeline_model}")
    if not vlm_model.exists():
        print(f"[WARN] VLM 模型不存在: {vlm_model}")
    
    # 更新 mineru.json 中的 models-dir 为绝对路径
    try:
        if default_config_path.exists():
            with open(default_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 更新 models-dir 为绝对路径
            config["models-dir"] = {
                "pipeline": str(pipeline_model),
                "vlm": str(vlm_model)
            }
            
            # 写回文件
            with open(default_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            
            print(f"[INFO] 已更新 mineru.json 模型路径: {models_dir}")
        else:
            print(f"[WARN] mineru.json 不存在: {default_config_path}")
    except Exception as e:
        print(f"[ERROR] 更新 mineru.json 失败: {e}")
    
    return str(default_config_path)


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
