#!/usr/bin/env python3
"""
后端启动脚本
自动设置环境并启动服务
"""
import os
import sys
import subprocess
from pathlib import Path


def check_venv():
    """检查是否在虚拟环境中"""
    return hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    )


def setup_venv(backend_dir: Path):
    """设置虚拟环境"""
    venv_dir = backend_dir / ".venv"
    
    if not venv_dir.exists():
        print("[RESTART] 创建虚拟环境...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    
    # 获取虚拟环境的 Python 路径
    if sys.platform == "win32":
        python_path = venv_dir / "Scripts" / "python.exe"
    else:
        python_path = venv_dir / "bin" / "python3"
    
    return python_path


def install_dependencies(python_path: Path, backend_dir: Path):
    """安装依赖"""
    requirements = backend_dir / "requirements.txt"
    
    if not requirements.exists():
        print("[WARN] 未找到 requirements.txt")
        return
    
    print("[RESTART] 安装依赖...")
    subprocess.run(
        [str(python_path), "-m", "pip", "install", "-r", str(requirements)],
        check=True
    )


def main():
    """主函数"""
    import signal
    import atexit
    
    backend_dir = Path(__file__).parent
    
    # 加载 .env 文件
    try:
        from dotenv import load_dotenv
        env_path = backend_dir / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)
            print(f"[OK] 已加载环境变量: {env_path}")
    except ImportError:
        pass  # dotenv 未安装时跳过
    
    # 启动前执行清理
    print("[CLEAN] 启动前清理环境...")
    cleanup_script = backend_dir / "cleanup.py"
    if cleanup_script.exists():
        try:
            subprocess.run([sys.executable, str(cleanup_script)], check=False, timeout=30)
            print()
        except Exception as e:
            print(f"[WARN] 清理脚本执行失败: {e}\n")
    
    print("=" * 50)
    print("知识库后端启动工具")
    print("=" * 50)
    
    # 检查虚拟环境
    if check_venv():
        print("[OK] 已在虚拟环境中")
        python_path = Path(sys.executable)
    else:
        print("[RESTART] 使用虚拟环境")
        python_path = setup_venv(backend_dir)
        install_dependencies(python_path, backend_dir)
    
    # 设置环境变量
    env = os.environ.copy()
    # USE_EMBEDDED_PG 从环境变量读取，如果不存在则默认使用嵌入式模式
    if "USE_EMBEDDED_PG" not in env:
        env["USE_EMBEDDED_PG"] = "true"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    
    # 启动服务
    print("\n[START] 启动后端服务...\n")
    main_py = backend_dir / "main.py"
    
    # 存储进程对象
    process = None
    
    def cleanup():
        """清理函数，确保子进程被终止"""
        nonlocal process
        if process and process.poll() is None:
            print("\n[STOP] 正在终止服务进程...")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("[WARN] 进程未响应，强制终止...")
                process.kill()
                process.wait()
            print("[OK] 服务进程已终止")
    
    def signal_handler(sig, frame):
        """信号处理函数"""
        print(f"\n[STOP] 接收到信号 {sig}")
        cleanup()
        sys.exit(0)
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 注册退出清理函数
    atexit.register(cleanup)
    
    try:
        process = subprocess.Popen(
            [str(python_path), str(main_py)],
            env=env,
            cwd=backend_dir
        )
        
        # 等待进程结束
        process.wait()
        
    except KeyboardInterrupt:
        print("\n[BYE] 接收到键盘中断")
        cleanup()
    except Exception as e:
        print(f"\n[ERROR] 服务运行错误: {e}")
        cleanup()
    finally:
        atexit.unregister(cleanup)


if __name__ == "__main__":
    main()
