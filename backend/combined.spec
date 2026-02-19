# -*- mode: python ; coding: utf-8 -*-
"""
Uverse Backend + PDF Worker 合并打包 Spec
两个可执行文件共享同一个 _internal 库目录
"""
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

# 多进程冻结支持
import multiprocessing
multiprocessing.freeze_support()

backend_dir = Path(os.path.dirname(os.path.abspath(SPEC)))
venv_path = backend_dir / '.venv' / 'lib' / 'python3.10' / 'site-packages'

block_cipher = None

# ============================================
# 使用 collect_all 收集完整包（确保所有子模块都被包含）
# ============================================

def collect_package(package_name):
    """收集完整包并返回 (datas, binaries, hiddenimports)"""
    try:
        datas, binaries, hiddenimports = collect_all(package_name)
        print(f"✅ 已收集 {package_name}: {len(datas)} datas, {len(binaries)} binaries, {len(hiddenimports)} hiddenimports")
        return datas, binaries, hiddenimports
    except Exception as e:
        print(f"⚠️  收集 {package_name} 失败: {e}")
        return [], [], []

# 收集所有关键包
all_datas = []
all_binaries = []
all_hiddenimports = []

# 核心 HTTP 库（requests 依赖链）
for pkg in ['requests', 'urllib3', 'charset_normalizer', 'idna', 'certifi']:
    d, b, h = collect_package(pkg)
    all_datas += d
    all_binaries += b
    all_hiddenimports += h

# AWS SDK
for pkg in ['boto3', 'botocore', 's3transfer', 'jmespath']:
    d, b, h = collect_package(pkg)
    all_datas += d
    all_binaries += b
    all_hiddenimports += h

# MinerU 及其依赖
for pkg in ['mineru', 'magika', 'loguru']:
    d, b, h = collect_package(pkg)
    all_datas += d
    all_binaries += b
    all_hiddenimports += h

# 数据处理/科学计算
for pkg in ['numpy', 'pandas', 'scipy', 'PIL', 'matplotlib', 'pydantic', 'pydantic_core']:
    d, b, h = collect_package(pkg)
    all_datas += d
    all_binaries += b
    all_hiddenimports += h

# AI/ML
for pkg in ['torch', 'torchvision', 'transformers', 'tokenizers', 'safetensors', 
            'accelerate', 'huggingface_hub', 'einops']:
    d, b, h = collect_package(pkg)
    all_datas += d
    all_binaries += b
    all_hiddenimports += h

# PDF 处理
for pkg in ['pypdf', 'pypdfium2', 'pdftext', 'pikepdf']:
    d, b, h = collect_package(pkg)
    all_datas += d
    all_binaries += b
    all_hiddenimports += h

# 图像处理
for pkg in ['skimage', 'doclayout_yolo', 'ultralytics', 'albumentations']:
    d, b, h = collect_package(pkg)
    all_datas += d
    all_binaries += b
    all_hiddenimports += h

# 工具库
for pkg in ['tqdm', 'click', 'fast_langdetect', 'rapid_table', 'shapely']:
    d, b, h = collect_package(pkg)
    all_datas += d
    all_binaries += b
    all_hiddenimports += h

# 配置/解析
for pkg in ['yaml', 'toml', 'tomli', 'tomli_w']:
    d, b, h = collect_package(pkg)
    all_datas += d
    all_binaries += b
    all_hiddenimports += h

# 其他重要依赖（使用正确的 pip 包名）
for pkg in ['aiohttp', 'aiofiles', 'ftfy', 'regex', 'tenacity', 'dill', 'attrs',
            'python-dateutil', 'python-dotenv', 'typing_extensions', 'filelock', 
            'lazy_loader', 'fasttext-predict', 'omegaconf', 'antlr4-python3-runtime',
            'psutil', 'pytz', 'tzdata', 'six', 'packaging', 'pyyaml']:
    d, b, h = collect_package(pkg)
    all_datas += d
    all_binaries += b
    all_hiddenimports += h

# ============================================
# 手动添加数据文件
# ============================================

# pdf_cli_wrapper.py 脚本
datas_main = [(str(backend_dir / 'workers/pdf_wrapper.py'), '.')]

# 手动添加单文件模块（collect_all 可能遗漏的）
for single_file in ['typing_extensions.py', 'six.py']:
    src = venv_path / single_file
    if src.exists():
        datas_main.append((str(src), '.'))

# 手动添加 dotenv 目录
if (venv_path / 'dotenv').exists():
    datas_main.append((str(venv_path / 'dotenv'), 'dotenv'))

# 手动添加 dateutil 完整目录
if (venv_path / 'dateutil').exists():
    import shutil
    # 复制整个 dateutil 目录
    for item in (venv_path / 'dateutil').rglob('*'):
        if item.is_file() and '__pycache__' not in str(item):
            rel_path = item.relative_to(venv_path)
            datas_main.append((str(item), str(rel_path.parent)))

# magika 模型
magika_model_path = venv_path / 'magika' / 'models' / 'standard_v3_3'
if magika_model_path.exists():
    datas_main.append((str(magika_model_path), 'magika/models/standard_v3_3'))

# 合并所有收集的数据
all_datas += datas_main

# 添加额外的数据文件
all_datas += collect_data_files('matplotlib', includes=['**/*.ttf', '**/*.otf', '**/*.afm', '**/*.json', 'matplotlibrc'])
all_datas += collect_data_files('fast_langdetect', includes=['**/*.ftz', '**/*.bin'])
all_datas += collect_data_files('skimage', includes=['**/*.txt', '**/*.npy'])
all_datas += collect_data_files('reportlab', includes=['**/*.ttf', '**/*.afm'])

# 添加二进制库目录
for lib_dir in ['scipy/.dylibs', 'cv2/.dylibs', 'av/.dylibs']:
    lib_path = venv_path / lib_dir
    if lib_path.exists():
        all_datas.append((str(lib_path), lib_dir))

# onnxruntime 二进制库
onnxruntime_libs = venv_path / 'onnxruntime' / 'capi'
if onnxruntime_libs.exists():
    for f in onnxruntime_libs.glob('*.dylib*'):
        if f.is_file():
            all_datas.append((str(f), 'onnxruntime/capi'))
    for f in onnxruntime_libs.glob('*.so*'):
        if f.is_file():
            all_datas.append((str(f), 'onnxruntime/capi'))

# doclayout_yolo 配置
doclayout_cfg_path = venv_path / 'doclayout_yolo' / 'cfg'
if doclayout_cfg_path.exists():
    all_datas.append((str(doclayout_cfg_path), 'doclayout_yolo/cfg'))

# ============================================
# 定义共享的 hiddenimports
# ============================================

SHARED_HIDDENIMPORTS = all_hiddenimports + [
    # Web 框架
    'fastapi', 'starlette', 'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
    'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on',
    
    # 数据库
    'sqlalchemy', 'sqlalchemy.ext.asyncio', 'sqlalchemy.dialects.postgresql', 
    'sqlalchemy.dialects.postgresql.asyncpg', 'asyncpg', 'pgvector', 'pgvector.sqlalchemy',
    
    # 数据验证
    'pydantic', 'pydantic_settings', 'pydantic.deprecated.decorator', 
    'pydantic_core', 'pydantic_core._pydantic_core',
    'annotated_types', 'typing_extensions', 'typing_inspection',
    
    # 配置
    'dotenv', 'python_dotenv',
    
    # LangChain
    'langchain', 'langchain_community', 'langchain_openai', 'openai',
    
    # 文档处理
    'fitz', 'pymupdf', 'docx', 'python_docx', 'chardet',
    
    # 文本处理
    'lxml', 'lxml.etree', 'bs4', 'beautifulsoup4', 'soupsieve',
    'json_repair', 'ftfy',
    
    # 工具
    'psutil', 'packaging', 'filelock', 'fsspec', 'hf_xet',
    'colorlog', 'humanfriendly', 'flatbuffers', 'coloredlogs', 'six',
    'exceptiongroup',
    
    # 多进程
    'multiprocessing', 'multiprocessing.pool', 'multiprocessing.process', 
    'multiprocessing.context', 'multiprocessing.reduction',
    'concurrent.futures', 'concurrent.futures.thread', 'concurrent.futures.process',
    
    # 网络/HTTP（补充）
    'httpx', 'httpcore', 'h11', 'anyio', 'sniffio', 'distro', 'jiter',
    'dateutil', 'dateutil.parser',
    
    # 压缩
    'brotli', 'zstandard', 'lz4',
    
    # 其他
    'cffi', 'pycparser',
]

# ============================================
# uverse-backend Analysis
# ============================================
a_main = Analysis(
    [str(backend_dir / 'main.py')],
    pathex=[str(backend_dir)],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=SHARED_HIDDENIMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(backend_dir / 'runtime_hook.py')],
    excludes=['tkinter', 'numpy.random._examples', 'PIL.ImageQt', 'PIL.ImageTk', 
              'PyQt5', 'PyQt6', 'PySide2', 'PySide6'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ============================================
# pdf-worker Analysis（使用相同的依赖）
# ============================================
a_worker = Analysis(
    [str(backend_dir / 'workers/pdf_wrapper.py')],
    pathex=[str(backend_dir)],
    binaries=[],  # 二进制文件已在主程序中
    datas=[],     # 数据文件已在主程序中
    hiddenimports=SHARED_HIDDENIMPORTS,  # 使用完全相同的依赖列表
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(backend_dir / 'runtime_hook.py')],
    excludes=['tkinter', 'numpy.random._examples', 'PIL.ImageQt', 'PIL.ImageTk', 
              'PyQt5', 'PySide6', 'PySide2', 'PySide6'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ============================================
# 合并 Analysis（共享库）
# ============================================
pyz_main = PYZ(a_main.pure, a_main.zipped_data, cipher=block_cipher)
pyz_worker = PYZ(a_worker.pure, a_worker.zipped_data, cipher=block_cipher)

exe_main = EXE(
    pyz_main,
    a_main.scripts,
    [],
    exclude_binaries=True,
    name='uverse-backend',
    debug=False,
    bootloader_ignore_signals=True,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

exe_worker = EXE(
    pyz_worker,
    a_worker.scripts,
    [],
    exclude_binaries=True,
    name='pdf-worker',
    debug=False,
    bootloader_ignore_signals=True,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# 合并收集到同一个目录（共享 _internal）
coll = COLLECT(
    exe_main,
    exe_worker,
    a_main.binaries,
    a_main.zipfiles,
    a_main.datas,
    a_worker.binaries,
    a_worker.zipfiles,
    a_worker.datas,
    strip=False,
    upx=False,
    name='uverse-backend'
)
