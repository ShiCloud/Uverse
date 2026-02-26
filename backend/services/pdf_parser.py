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


def _is_relative_subpath(path_str: str) -> bool:
    """检查路径是否为相对子路径（不是绝对路径，不以 / 或 盘符开头）"""
    if not path_str:
        return False
    # Windows: 检查盘符，如 C:\
    if len(path_str) >= 2 and path_str[1] == ':':
        return False
    # Unix/Windows: 检查是否以 / 或 \ 开头
    if path_str.startswith('/') or path_str.startswith('\\'):
        return False
    return True


def get_mineru_config_path() -> str:
    """
    获取 MinerU 配置文件路径
    
    必须配置 MODELS_DIR 环境变量，且该目录下必须包含 mineru.json
    如果 mineru.json 中的 models-dir 是相对路径，
    且与 mineru.json 同级目录，则更新为绝对路径
    
    Raises:
        Exception: 如果 MODELS_DIR 未配置或 mineru.json 不存在
    """
    models_dir_env = os.getenv("MODELS_DIR")
    
    # 步骤 1: 检查 MODELS_DIR 是否配置
    if not models_dir_env:
        raise Exception("MODELS_DIR 环境变量未配置，无法找到 mineru.json")
    
    # 步骤 2: 解析 MODELS_DIR 路径
    try:
        if os.path.isabs(models_dir_env):
            models_dir = Path(models_dir_env)
        else:
            backend_dir = Path(__file__).parent.parent
            models_dir = backend_dir / models_dir_env
        models_dir = models_dir.resolve()
    except Exception as e:
        raise Exception(f"解析 MODELS_DIR 失败: {e}")
    
    # 步骤 3: 检查 MODELS_DIR 下是否有 mineru.json
    config_path = models_dir / "mineru.json"
    if not config_path.exists():
        raise Exception(f"mineru.json 不存在于 MODELS_DIR: {config_path}，请确保模型目录配置正确")
    
    print(f"[INFO] 使用 MODELS_DIR 下的 mineru.json: {config_path}")
    
    # 步骤 4: 读取配置并更新为基于当前 MODELS_DIR 的正确绝对路径
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        models_dir_config = config.get("models-dir", {})
        pipeline_path = models_dir_config.get("pipeline", "")
        vlm_path = models_dir_config.get("vlm", "")
        
        print(f"[DEBUG] 当前 models-dir: pipeline={pipeline_path}, vlm={vlm_path}")
        print(f"[DEBUG] models_dir (MODELS_DIR): {models_dir}")
        
        updated = False
        
        # 定义标准模型路径（基于当前 MODELS_DIR）
        standard_pipeline = models_dir / "OpenDataLab" / "PDF-Extract-Kit-1___0"
        standard_vlm = models_dir / "OpenDataLab" / "MinerU2___5-2509-1___2B"
        
        # 更新 pipeline 路径
        if pipeline_path:
            # 检查是否为相对路径
            is_relative = _is_relative_subpath(pipeline_path)
            
            if is_relative:
                # 相对路径：解析为基于 MODELS_DIR 的绝对路径
                expected_path = models_dir / pipeline_path
                print(f"[DEBUG] pipeline relative, expected_path={expected_path}")
                
                if expected_path.exists():
                    models_dir_config["pipeline"] = str(expected_path.resolve())
                    updated = True
                    print(f"[INFO] 更新 pipeline 为绝对路径: {models_dir_config['pipeline']}")
                else:
                    print(f"[WARN] pipeline 路径不存在: {expected_path}")
            else:
                # 绝对路径：检查是否需要更新为当前 MODELS_DIR 下的标准路径
                current_path = Path(pipeline_path)
                if current_path.exists():
                    # 路径有效，但仍检查是否应该使用标准路径
                    if standard_pipeline.exists() and current_path != standard_pipeline:
                        models_dir_config["pipeline"] = str(standard_pipeline.resolve())
                        updated = True
                        print(f"[INFO] 更新 pipeline 为标准路径: {models_dir_config['pipeline']}")
                    else:
                        print(f"[DEBUG] pipeline 路径有效，无需更新: {pipeline_path}")
                else:
                    # 路径无效（可能是旧位置的绝对路径），尝试使用标准路径
                    print(f"[WARN] pipeline 路径无效: {pipeline_path}")
                    if standard_pipeline.exists():
                        models_dir_config["pipeline"] = str(standard_pipeline.resolve())
                        updated = True
                        print(f"[INFO] 更新 pipeline 为标准路径: {models_dir_config['pipeline']}")
        else:
            # pipeline 为空，尝试设置为标准路径
            if standard_pipeline.exists():
                models_dir_config["pipeline"] = str(standard_pipeline.resolve())
                updated = True
                print(f"[INFO] 设置 pipeline 为标准路径: {models_dir_config['pipeline']}")
        
        # 更新 vlm 路径（逻辑相同）
        if vlm_path:
            is_relative = _is_relative_subpath(vlm_path)
            
            if is_relative:
                expected_path = models_dir / vlm_path
                print(f"[DEBUG] vlm relative, expected_path={expected_path}")
                
                if expected_path.exists():
                    models_dir_config["vlm"] = str(expected_path.resolve())
                    updated = True
                    print(f"[INFO] 更新 vlm 为绝对路径: {models_dir_config['vlm']}")
                else:
                    print(f"[WARN] vlm 路径不存在: {expected_path}")
            else:
                current_path = Path(vlm_path)
                if current_path.exists():
                    if standard_vlm.exists() and current_path != standard_vlm:
                        models_dir_config["vlm"] = str(standard_vlm.resolve())
                        updated = True
                        print(f"[INFO] 更新 vlm 为标准路径: {models_dir_config['vlm']}")
                    else:
                        print(f"[DEBUG] vlm 路径有效，无需更新: {vlm_path}")
                else:
                    print(f"[WARN] vlm 路径无效: {vlm_path}")
                    if standard_vlm.exists():
                        models_dir_config["vlm"] = str(standard_vlm.resolve())
                        updated = True
                        print(f"[INFO] 更新 vlm 为标准路径: {models_dir_config['vlm']}")
        else:
            if standard_vlm.exists():
                models_dir_config["vlm"] = str(standard_vlm.resolve())
                updated = True
                print(f"[INFO] 设置 vlm 为标准路径: {models_dir_config['vlm']}")
        
        # 写回文件
        if updated:
            config["models-dir"] = models_dir_config
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            print(f"[INFO] 已更新 mineru.json 中的模型路径")
        else:
            print(f"[INFO] mineru.json 路径配置正确")
    except Exception as e:
        print(f"[ERROR] 读取或更新 mineru.json 失败: {e}")
        import traceback
        traceback.print_exc()
    
    return str(config_path)


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
