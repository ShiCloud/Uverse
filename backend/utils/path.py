"""
路径工具模块 - 统一处理路径解析和检查
"""
import os
from pathlib import Path
from typing import Optional


def resolve_path(path_str: str, base_dir: Optional[Path] = None) -> Optional[Path]:
    """
    解析路径（支持相对路径和绝对路径）
    
    Args:
        path_str: 路径字符串
        base_dir: 基础目录（用于相对路径），默认为 None
        
    Returns:
        解析后的 Path 对象，如果 path_str 为空则返回 None
    """
    if not path_str or not path_str.strip():
        return None
    
    # 清理路径字符串（移除首尾空格和引号）
    cleaned_path = path_str.strip().strip('"\'')
    
    # 处理 Windows 路径的反斜杠，统一转换为正斜杠以便跨平台处理
    # 但保留原始格式用于显示
    cleaned_path = cleaned_path.replace('\\', '/')
    
    path = Path(cleaned_path)
    
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    
    try:
        # 使用 resolve() 获取绝对路径，如果路径不存在也不会抛出异常
        return path.resolve()
    except Exception:
        # 如果 resolve 失败，返回原始路径
        return path


def check_executable(base_path: Path, name: str, is_windows: Optional[bool] = None) -> bool:
    """
    检查可执行文件是否存在
    
    Args:
        base_path: 基础目录
        name: 可执行文件名（不含扩展名）
        is_windows: 是否为 Windows 系统，自动检测
        
    Returns:
        文件是否存在
    """
    if is_windows is None:
        is_windows = os.name == 'nt'
    
    exe_name = f"{name}.exe" if is_windows else name
    exe_path = base_path / exe_name
    return exe_path.exists()


def check_subdir(base_path: Path, subdir: str) -> bool:
    """
    检查子目录是否存在
    
    Args:
        base_path: 基础目录
        subdir: 子目录名称
        
    Returns:
        子目录是否存在
    """
    subdir_path = base_path / subdir
    return subdir_path.exists() and subdir_path.is_dir()


def get_user_data_dir(app_name: str = "Uverse") -> Path:
    """
    获取用户数据目录
    
    Args:
        app_name: 应用名称
        
    Returns:
        用户数据目录路径
    """
    if os.name == 'nt':  # Windows
        base_dir = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif os.uname().sysname == 'Darwin':  # macOS
        base_dir = Path.home() / 'Library' / 'Application Support'
    else:  # Linux
        base_dir = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    
    return base_dir / app_name


def get_default_dir(subdir: str, app_name: str = "Uverse") -> Path:
    """
    获取默认子目录路径
    
    Args:
        subdir: 子目录名称
        app_name: 应用名称
        
    Returns:
        默认目录路径
    """
    return get_user_data_dir(app_name) / subdir


def get_exe_dir() -> Path:
    """
    获取可执行文件所在目录
    
    在 PyInstaller 打包模式下，返回 exe 文件所在目录
    在开发模式下，返回当前文件所在目录
    
    Returns:
        可执行文件目录路径
    """
    import sys
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包模式：使用 sys.executable 获取 exe 目录
        return Path(sys.executable).parent
    else:
        # 开发模式：使用当前文件所在目录
        return Path(__file__).parent.parent


def resolve_path_for_config(path_str: str, backend_dir: Optional[Path] = None) -> Optional[Path]:
    """
    解析配置路径（支持相对路径和绝对路径）
    
    Windows 打包模式下的特殊处理（其他平台保持原有逻辑）：
    - 如果是相对路径，优先检查 exe 目录下的相对目录
    - 如果该目录存在且合法，返回该路径
    - 否则，使用传入的 base_dir 或默认后端目录解析
    
    Args:
        path_str: 路径字符串
        backend_dir: 基础目录（用于相对路径），默认为 None
        
    Returns:
        解析后的 Path 对象，如果 path_str 为空则返回 None
    """
    import sys
    
    if not path_str or not path_str.strip():
        return None
    
    # 清理路径字符串
    cleaned_path = path_str.strip().strip('"\'').replace('\\', '/')
    path = Path(cleaned_path)
    
    # 绝对路径直接返回
    if path.is_absolute():
        return path.resolve()
    
    # Windows 打包模式下的特殊处理
    # 只有 Windows 环境才检查 exe 目录下的相对目录
    if os.name == 'nt' and getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        exe_relative_path = exe_dir / cleaned_path
        
        # 检查目录是否存在且非空
        if exe_relative_path.exists():
            try:
                # 检查目录是否非空（有内容）
                if exe_relative_path.is_dir() and any(exe_relative_path.iterdir()):
                    return exe_relative_path.resolve()
            except (OSError, PermissionError):
                pass
    
    # 使用传入的 base_dir 或当前工作目录
    if backend_dir is not None:
        path = backend_dir / path
    
    try:
        return path.resolve()
    except Exception:
        return path
