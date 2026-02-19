#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF 解析工作进程 - 独立进程执行 MinerU 解析
作为可执行文件直接运行，不需要外部 Python

注意：此文件主要用于打包后的独立进程模式。
新的线程池方案（process_pool.py）通常更推荐使用。
"""
import os
import sys

# 设置 Python 使用 UTF-8 编码
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'

# PyInstaller 兼容性 - 必须在任何其他导入之前调用
try:
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass
except ImportError:
    pass


def parse_pdf_sync(
    pdf_path: str,
    doc_id: str,
    output_dir: str,
    config_path: str,
    device: str = "cpu"
) -> dict:
    """
    同步执行 PDF 解析
    
    Args:
        pdf_path: PDF 文件路径
        doc_id: 文档 ID
        output_dir: 输出目录
        config_path: MinerU 配置文件路径
        device: 设备模式 (cpu/cuda)
    
    Returns:
        解析结果字典
    """
    from pathlib import Path
    
    try:
        # 设置环境变量 - 禁用多进程
        os.environ["MINERU_TOOLS_CONFIG_JSON"] = config_path
        os.environ['MINERU_DEVICE_MODE'] = device
        os.environ['MINERU_MODEL_SOURCE'] = 'local'
        os.environ["MINERU_PDF_RENDER_THREADS"] = "1"
        
        # Monkey-patch: 让 MinerU 认为是 Windows 环境
        import mineru.utils.check_sys_env
        mineru.utils.check_sys_env.is_windows_environment = lambda: True
        
        # 导入 MinerU
        from mineru.cli.common import do_parse, read_fn
        
        # 创建输出目录
        doc_output_dir = Path(output_dir) / doc_id
        doc_output_dir.mkdir(parents=True, exist_ok=True)
        
        # 读取 PDF
        pdf_bytes = read_fn(pdf_path)
        pdf_file_name = Path(pdf_path).stem
        
        # 执行解析
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
        
        # 查找生成的 Markdown 文件
        md_file = None
        for f in doc_output_dir.rglob("*.md"):
            md_file = str(f)
            break
        
        # 查找图片目录
        images_dir = doc_output_dir / "images"
        if not images_dir.exists():
            for subdir in doc_output_dir.rglob("images"):
                if subdir.is_dir():
                    images_dir = subdir
                    break
        
        # 输出结果
        result = {
            "success": True,
            "output_dir": str(doc_output_dir),
            "markdown_file": md_file,
            "images_dir": str(images_dir) if images_dir.exists() else None,
        }
        return result
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return {
            "success": False,
            "error": str(e),
            "traceback": error_detail
        }


def main():
    """主函数 - 解析命令行参数并执行解析"""
    import json
    
    if len(sys.argv) < 6:
        print(json.dumps({"success": False, "error": "参数不足"}), file=sys.stderr)
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    doc_id = sys.argv[2]
    output_dir = sys.argv[3]
    config_path = sys.argv[4]
    device = sys.argv[5] if len(sys.argv) > 5 else "cpu"
    
    result = parse_pdf_sync(pdf_path, doc_id, output_dir, config_path, device)
    
    if result["success"]:
        print(json.dumps(result))
        sys.exit(0)
    else:
        print(json.dumps(result), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
