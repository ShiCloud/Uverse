"""
Transformers 库补丁 - 修复 PyInstaller 打包后的 inspect.getsource 问题
"""
import inspect
import functools

# 保存原始的 getsource
try:
    _original_getsource = inspect.getsource
except AttributeError:
    _original_getsource = None

def _patched_getsource(obj, *args, **kwargs):
    """如果无法获取源代码，返回空字符串而不是抛出异常"""
    try:
        if _original_getsource:
            return _original_getsource(obj, *args, **kwargs)
    except (OSError, TypeError, IOError):
        pass
    return ""

def _patched_getsourcelines(obj, *args, **kwargs):
    """如果无法获取源代码行，返回 ([""], 0) 而不是抛出异常"""
    try:
        return inspect.getsourcelines(obj, *args, **kwargs)
    except (OSError, TypeError, IOError):
        return ([""], 0)

# 应用补丁
def apply_transformers_patch():
    """应用 transformers 补丁"""
    inspect.getsource = _patched_getsource
    inspect.getsourcelines = _patched_getsourcelines
    
    # 也尝试修补 transformers 的 doc.py
    try:
        from transformers.utils import doc
        if hasattr(doc, 'get_docstring_indentation_level'):
            original_func = doc.get_docstring_indentation_level
            
            @functools.wraps(original_func)
            def _patched_get_docstring_indentation_level(fn):
                try:
                    return original_func(fn)
                except OSError:
                    return 0
            
            doc.get_docstring_indentation_level = _patched_get_docstring_indentation_level
    except Exception:
        pass

# 自动应用补丁
apply_transformers_patch()
