"""
PyInstaller 运行时钩子 - 处理多进程兼容性
"""
import sys
import os

# 修复 PyInstaller 打包后的多进程问题
if hasattr(sys, '_MEIPASS'):
    # 设置 multiprocessing 启动方法
    import multiprocessing
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass  # 已经设置过了
    
    # 设置环境变量，确保子进程能找到资源
    os.environ['PYTHONPATH'] = sys._MEIPASS
    
    # 修复某些库的路径问题
    if sys.platform == 'darwin':  # macOS
        os.environ['DYLD_LIBRARY_PATH'] = os.path.join(sys._MEIPASS, 'lib') + ':' + os.environ.get('DYLD_LIBRARY_PATH', '')
    
    # ========== Transformers 补丁 ==========
    # 修复 PyInstaller 打包后的 inspect.getsource 问题
    # 必须在导入 transformers 之前应用
    import inspect
    import functools
    
    # 保存原始函数
    _original_getsource = inspect.getsource
    _original_getsourcelines = inspect.getsourcelines
    
    # 返回一个有效但无用的源代码字符串
    _DUMMY_SOURCE = '''def dummy():
    """Dummy function for PyInstaller compatibility."""
    pass
'''
    
    def _patched_getsource(obj, *args, **kwargs):
        """如果无法获取源代码，返回虚拟源代码字符串"""
        try:
            return _original_getsource(obj, *args, **kwargs)
        except (OSError, TypeError, IOError):
            return _DUMMY_SOURCE
    
    def _patched_getsourcelines(obj, *args, **kwargs):
        """如果无法获取源代码行，返回虚拟源代码行"""
        try:
            return _original_getsourcelines(obj, *args, **kwargs)
        except (OSError, TypeError, IOError):
            lines = _DUMMY_SOURCE.splitlines(True)  # 保留换行符
            return (lines, 1)
    
    # 应用补丁
    inspect.getsource = _patched_getsource
    inspect.getsourcelines = _patched_getsourcelines
