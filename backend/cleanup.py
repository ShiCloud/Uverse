#!/usr/bin/env python3
"""
智能清理脚本 - 只清理有问题的残留进程
在启动服务前执行，确保环境干净
"""
import os
import sys
import subprocess
import signal
import time
from pathlib import Path


def get_temp_dir() -> Path:
    """获取临时目录路径 - 优先使用环境变量 TEMP_DIR"""
    temp_dir_env = os.getenv('TEMP_DIR')
    if temp_dir_env:
        return Path(temp_dir_env)
    
    # 默认使用用户可写目录
    if os.name == 'nt':  # Windows
        base_dir = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif os.uname().sysname == 'Darwin':  # macOS
        base_dir = Path.home() / 'Library' / 'Application Support'
    else:  # Linux
        base_dir = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return base_dir / 'Uverse' / 'temp'


# 配置
TARGET_PORTS = [8000, 9000, 15432]  # 需要检查的端口
# 注意：postgres 进程只在嵌入式模式下清理，外部数据库模式下跳过
TARGET_NAMES = ['rustfs', 'postgres']  # 需要检查的进程名
MAX_WAIT_TIME = 5  # 等待进程终止的最大时间（秒）

# 导入公共工具（使用局部导入避免循环依赖）
def is_external_db_mode():
    """检查是否使用外部数据库模式"""
    return os.getenv('USE_EMBEDDED_PG', 'true').lower() == 'false'


def run_command(cmd, capture=True, timeout=3):
    """运行命令并返回结果"""
    try:
        if capture:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return result.stdout.strip()
        else:
            subprocess.run(cmd, shell=True, timeout=timeout)
            return ""
    except subprocess.TimeoutExpired:
        return ""
    except Exception as e:
        return f""


def is_process_responsive(pid):
    """检查进程是否响应（是否卡死）"""
    try:
        # 发送信号 0 检查进程是否存在
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def get_process_info(pid):
    """获取进程信息"""
    try:
        # macOS
        if sys.platform == "darwin":
            output = run_command(f"ps -p {pid} -o pid,ppid,comm,args", timeout=2)
            lines = output.strip().split('\n')
            if len(lines) >= 2:
                return lines[1]
        # Linux
        elif sys.platform.startswith("linux"):
            output = run_command(f"ps -p {pid} -o pid,ppid,cmd", timeout=2)
            lines = output.strip().split('\n')
            if len(lines) >= 2:
                return lines[1]
    except:
        pass
    return None


def is_our_process(pid):
    """检查进程是否是我们的应用进程（根据工作目录或命令行）"""
    try:
        info = get_process_info(pid)
        if not info:
            return False
        
        # 检查是否包含我们的项目路径
        our_paths = [
            'Uverse',
            'uverse',
            'backend/main.py',
            'rustfs',
            'postgres',
        ]
        
        for path in our_paths:
            if path in info:
                return True
        
        return False
    except:
        return False


def kill_process_gracefully(pid, name=""):
    """优雅地终止进程"""
    name_str = f" ({name})" if name else ""
    
    # 检查进程是否存在
    if not is_process_responsive(pid):
        print(f"  ℹ️ 进程 PID {pid}{name_str} 已不存在")
        return True
    
    # 检查是否是我们的进程
    if not is_our_process(pid):
        print(f"  ⚠️ 进程 PID {pid}{name_str} 不是我们的应用进程，跳过")
        return False
    
    print(f"  🛑 正在终止进程 PID {pid}{name_str}")
    
    # 先尝试 SIGTERM (优雅终止)
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception as e:
        print(f"  ⚠️ 发送 SIGTERM 失败: {e}")
    
    # 等待进程终止
    start_time = time.time()
    while time.time() - start_time < MAX_WAIT_TIME:
        if not is_process_responsive(pid):
            print(f"  ✅ 进程 PID {pid} 已终止")
            return True
        time.sleep(0.5)
    
    # 如果还在运行，强制终止
    print(f"  ⚠️ 进程 PID {pid} 未响应，强制终止...")
    try:
        os.kill(pid, signal.SIGKILL)
        time.sleep(1)
        if not is_process_responsive(pid):
            print(f"  ✅ 进程 PID {pid} 已强制终止")
            return True
    except Exception as e:
        print(f"  ❌ 强制终止失败: {e}")
    
    return False


def check_port_usage(port):
    """检查端口使用情况，返回使用该端口的进程 PID 列表"""
    pids = []
    
    if sys.platform == "darwin" or sys.platform.startswith("linux"):
        # 使用 lsof 查找占用端口的进程
        output = run_command(f"lsof -ti:{port}", timeout=3)
        if output:
            for line in output.split('\n'):
                line = line.strip()
                if line.isdigit():
                    pid = int(line)
                    pids.append(pid)
    
    return pids


def cleanup_ports():
    """清理占用目标端口的进程"""
    print("🔍 检查端口占用情况...")
    
    killed_count = 0
    skipped_count = 0
    external_db_mode = is_external_db_mode()
    
    for port in TARGET_PORTS:
        # 外部数据库模式下，跳过 PostgreSQL 端口检查（5432/15432）
        # 注意：15432 是嵌入式 PostgreSQL 的默认端口，5432 是标准端口
        if external_db_mode and port == 15432:
            print(f"  ℹ️  外部数据库模式，跳过端口 {port} 检查")
            continue
        
        pids = check_port_usage(port)
        
        if not pids:
            print(f"  ✅ 端口 {port} 未被占用")
            continue
        
        print(f"  📍 端口 {port} 被 {len(pids)} 个进程占用")
        
        for pid in pids:
            # 不杀死当前进程
            if pid == os.getpid():
                print(f"  ℹ️ 跳过当前进程 PID {pid}")
                continue
            
            if kill_process_gracefully(pid, f"端口 {port}"):
                killed_count += 1
            else:
                skipped_count += 1
    
    return killed_count, skipped_count


def cleanup_by_name():
    """根据进程名清理"""
    print("🔍 检查目标进程...")
    
    killed_count = 0
    skipped_count = 0
    external_db_mode = is_external_db_mode()
    
    for name in TARGET_NAMES:
        # 外部数据库模式下，跳过 postgres 进程清理
        if name == 'postgres' and external_db_mode:
            print(f"  ℹ️  外部数据库模式，跳过 {name} 进程检查")
            continue
        
        if sys.platform == "darwin" or sys.platform.startswith("linux"):
            # 使用 pgrep 查找进程
            output = run_command(f"pgrep -f '{name}'", timeout=3)
            if not output:
                print(f"  ✅ 未发现残留进程: {name}")
                continue
            
            pids = [int(p.strip()) for p in output.split('\n') if p.strip().isdigit()]
            
            if not pids:
                print(f"  ✅ 未发现残留进程: {name}")
                continue
            
            print(f"  📍 发现 {len(pids)} 个 {name} 进程")
            
            for pid in pids:
                # 不杀死当前进程
                if pid == os.getpid():
                    continue
                
                if kill_process_gracefully(pid, name):
                    killed_count += 1
                else:
                    skipped_count += 1
    
    return killed_count, skipped_count


def cleanup_temp_files():
    """清理临时文件"""
    print("🔍 清理临时文件...")
    
    backend_dir = Path(__file__).parent
    cleaned = []
    
    # 清理 temp 目录
    temp_dir = get_temp_dir()
    if temp_dir.exists():
        import shutil
        try:
            shutil.rmtree(temp_dir)
            cleaned.append(str(temp_dir))
        except Exception as e:
            print(f"  ⚠️ 清理 {temp_dir} 失败: {e}")
    
    # 清理 out 目录中的旧文件（保留最近1小时的）
    out_dir = backend_dir / "out"
    if out_dir.exists():
        current_time = time.time()
        for item in out_dir.iterdir():
            try:
                # 检查文件/目录的修改时间
                stat = item.stat()
                age_hours = (current_time - stat.st_mtime) / 3600
                
                # 删除超过1小时的文件
                if age_hours > 1:
                    if item.is_dir():
                        import shutil
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    cleaned.append(str(item))
            except Exception as e:
                print(f"  ⚠️ 清理 {item} 失败: {e}")
    
    if cleaned:
        print(f"  ✅ 已清理 {len(cleaned)} 个临时文件/目录")
    else:
        print(f"  ✅ 无需清理临时文件")


def main():
    """主函数"""
    print("=" * 50)
    print("🧹 智能清理残留进程和文件")
    print("=" * 50)
    
    # 清理端口占用
    port_killed, port_skipped = cleanup_ports()
    
    print()
    
    # 清理目标进程
    name_killed, name_skipped = cleanup_by_name()
    
    print()
    
    # 清理临时文件
    cleanup_temp_files()
    
    print()
    print("=" * 50)
    total_killed = port_killed + name_killed
    total_skipped = port_skipped + name_skipped
    
    if total_killed > 0:
        print(f"✅ 已终止 {total_killed} 个进程")
    if total_skipped > 0:
        print(f"⚠️ 跳过 {total_skipped} 个进程（非本应用或无法终止）")
    if total_killed == 0 and total_skipped == 0:
        print("✅ 环境已干净，无需清理")
    
    print("=" * 50)


if __name__ == "__main__":
    main()
