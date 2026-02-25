#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF Worker 引导程序 - 支持热更新
1. 优先尝试加载外部的 pdf_wrapper.py（支持修改不重新打包）
2. 如果外部不存在，使用内置的代码
"""
import sys
import os
from pathlib import Path

def find_external_wrapper():
    """查找外部的 pdf_wrapper.py"""
    exe_dir = Path(sys.executable).parent
    
    possible_paths = [
        # 可执行文件同级目录下的 workers
        exe_dir / "workers" / "pdf_wrapper.py",
        # 父目录下的 workers（Electron 资源目录结构）
        exe_dir.parent / "workers" / "pdf_wrapper.py",
        # 上两级目录
        exe_dir.parent.parent / "workers" / "pdf_wrapper.py",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    return None

def main():
    """主入口"""
    external_path = find_external_wrapper()
    
    if external_path:
        # 使用外部脚本（支持热更新）
        # 输出到 stdout 而不是 stderr，避免被标记为 ERROR
        print(f"[pdf-worker] Loading external: {external_path}", flush=True)
        with open(external_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        # 设置执行环境
        script_globals = {
            '__name__': '__main__',
            '__file__': str(external_path),
        }
        exec(compile(code, str(external_path), 'exec'), script_globals)
    else:
        # 使用内置代码
        # 输出到 stdout 而不是 stderr，避免被标记为 ERROR
        print(f"[pdf-worker] Using built-in code", flush=True)
        # 导入并执行内置的 pdf_wrapper main 函数
        try:
            from workers.pdf_wrapper import main
            main()
        except ImportError:
            # 如果导入失败，尝试直接执行 __main__ 块
            import workers.pdf_wrapper
            if hasattr(workers.pdf_wrapper, 'main'):
                workers.pdf_wrapper.main()

if __name__ == '__main__':
    main()
