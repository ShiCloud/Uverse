"""
PostgreSQL 便携版管理模块
负责管理嵌入式 PostgreSQL 的启动、停止和初始化
"""
import os
import sys
import subprocess
import time
import signal
import atexit
import platform
from pathlib import Path
from typing import Optional


class PostgresManager:
    """PostgreSQL 便携版管理器"""
    
    def __init__(self):
        self.platform = platform.system()
        self.base_dir = Path(__file__).parent.parent
        
        # 从环境变量读取 PostgreSQL 目录，默认为相对路径
        pg_dir_env = os.getenv("POSTGRES_DIR", "postgres")
        if os.path.isabs(pg_dir_env):
            self.pg_dir = Path(pg_dir_env)
        else:
            # 相对路径，基于 backend 目录
            self.pg_dir = self.base_dir / pg_dir_env
        
        self.pg_bin_dir = self.pg_dir / "bin"
        self.data_dir = self.pg_dir / "data"
        self.log_file = self.pg_dir / "postgres.log"
        self.pid_file = self.pg_dir / "postgres.pid"
        self.process: Optional[subprocess.Popen] = None
        
        # 根据平台设置可执行文件路径
        if self.platform == "Windows":
            self.pg_ctl = self.pg_bin_dir / "pg_ctl.exe"
            self.postgres = self.pg_bin_dir / "postgres.exe"
            self.psql = self.pg_bin_dir / "psql.exe"
            self.initdb = self.pg_bin_dir / "initdb.exe"
        else:  # macOS / Linux
            self.pg_ctl = self.pg_bin_dir / "pg_ctl"
            self.postgres = self.pg_bin_dir / "postgres"
            self.psql = self.pg_bin_dir / "psql"
            self.initdb = self.pg_bin_dir / "initdb"
        
        # 默认配置（使用 DATABASE_ 前缀，与外部数据库配置统一）
        self.port = int(os.getenv("DATABASE_PORT", "15432"))  # 使用非标准端口避免冲突
        self.username = os.getenv("DATABASE_USER", "postgres")
        self.password = os.getenv("DATABASE_PASSWORD", "postgres")
        self.database = os.getenv("DATABASE_NAME", "knowledge_base")
        
    def is_installed(self) -> bool:
        """检查 PostgreSQL 便携版是否已安装"""
        return self.pg_ctl.exists() and self.initdb.exists()
    
    def is_initialized(self) -> bool:
        """检查数据库是否已初始化"""
        return self.data_dir.exists() and (self.data_dir / "PG_VERSION").exists()
    
    def is_running(self) -> bool:
        """检查 PostgreSQL 是否正在运行"""
        if not self.pid_file.exists():
            # 也尝试用 pg_ctl status 检查
            return self._check_status_via_pg_ctl()
        
        try:
            with open(self.pid_file, "r") as f:
                pid = int(f.read().strip())
            
            # 检查进程是否存在
            if self.platform == "Windows":
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True,
                    text=True
                )
                return str(pid) in result.stdout
            else:
                os.kill(pid, 0)
                return True
        except (ValueError, OSError, ProcessLookupError):
            return self._check_status_via_pg_ctl()
    
    def _check_status_via_pg_ctl(self) -> bool:
        """通过 pg_ctl status 检查状态"""
        try:
            result = subprocess.run(
                [str(self.pg_ctl), "status", "-D", str(self.data_dir)],
                capture_output=True,
                text=True,
                cwd=str(self.pg_bin_dir)
            )
            return result.returncode == 0 and "server is running" in result.stdout
        except Exception:
            return False
    
    def init_database(self) -> bool:
        """初始化数据库集群"""
        if not self.is_installed():
            print(f"❌ PostgreSQL 便携版未找到: {self.pg_dir}")
            return False
        
        if self.is_initialized():
            print("✅ 数据库已初始化")
            return True
        
        print("🔄 正在初始化 PostgreSQL 数据库...")
        
        # 创建数据目录
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 运行 initdb
        env = os.environ.copy()
        env["LC_ALL"] = "C"  # 避免本地化问题
        
        cmd = [
            str(self.initdb),
            "-D", str(self.data_dir),
            "-U", self.username,
            "--encoding=UTF8",
            "--locale=C",
            "--lc-collate=C",
            "--lc-ctype=C"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(self.pg_bin_dir)
            )
            
            if result.returncode != 0:
                print(f"❌ 初始化失败: {result.stderr}")
                return False
            
            # 设置密码 - 修改 pg_hba.conf 允许本地信任连接
            self._setup_hba_conf()
            
            print("✅ 数据库初始化完成")
            return True
            
        except Exception as e:
            print(f"❌ 初始化异常: {e}")
            return False
    
    def _setup_hba_conf(self):
        """设置 pg_hba.conf 允许本地连接"""
        hba_conf = self.data_dir / "pg_hba.conf"
        hba_content = """# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
"""
        with open(hba_conf, "w") as f:
            f.write(hba_content)
        print("✅ 已配置 pg_hba.conf")
    
    def _setup_postgresql_conf(self):
        """设置 postgresql.conf 配置端口"""
        conf_file = self.data_dir / "postgresql.conf"
        
        # 读取现有配置
        if conf_file.exists():
            with open(conf_file, "r") as f:
                lines = f.readlines()
        else:
            lines = []
        
        # 添加或修改端口配置
        port_config = f"port = {self.port}\n"
        listen_config = "listen_addresses = '127.0.0.1'\n"
        
        # 检查是否已有 port 配置
        has_port = False
        has_listen = False
        for i, line in enumerate(lines):
            if line.strip().startswith("port ="):
                lines[i] = port_config
                has_port = True
            if line.strip().startswith("listen_addresses ="):
                lines[i] = listen_config
                has_listen = True
        
        if not has_port:
            lines.append(f"\n# Custom port setting\n{port_config}")
        if not has_listen:
            lines.append(f"\n# Custom listen_addresses setting\n{listen_config}")
        
        with open(conf_file, "w") as f:
            f.writelines(lines)
        
        print(f"✅ 已配置 postgresql.conf (端口: {self.port})")
    
    def start(self) -> bool:
        """启动 PostgreSQL 服务 - 使用 pg_ctl 命令"""
        # 检查关键可执行文件是否存在
        if not self.is_installed():
            print(f"⚠️ PostgreSQL 可执行文件不存在: pg_ctl={self.pg_ctl}, initdb={self.initdb}")
            return False
        
        if self.is_running():
            print("✅ PostgreSQL 已在运行")
            return True
        
        if not self.is_initialized():
            if not self.init_database():
                return False
        
        # 配置 postgresql.conf
        self._setup_postgresql_conf()
        
        print("🚀 正在启动 PostgreSQL...")
        
        # 使用 pg_ctl start 命令启动
        # 命令格式: ./pg_ctl start -D "../data" -l logfile
        log_file_path = self.pg_dir / "logfile"
        
        cmd = [
            str(self.pg_ctl),
            "start",
            "-D", str(self.data_dir),
            "-l", str(log_file_path)
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.pg_bin_dir)
            )
            
            if result.returncode != 0:
                print(f"❌ 启动失败: {result.stderr}")
                return False
            
            # 等待数据库就绪
            if not self._wait_for_ready():
                print("❌ PostgreSQL 启动超时")
                return False
            
            # 创建数据库和用户
            self._create_database()
            
            # 保存 PID
            self._save_pid()
            
            # 注册退出时的清理函数
            atexit.register(self.stop)
            
            print(f"✅ PostgreSQL 已启动 (端口: {self.port})")
            return True
            
        except Exception as e:
            print(f"❌ 启动失败: {e}")
            return False
    
    def _save_pid(self):
        """保存 PostgreSQL 进程 PID"""
        # 从 postmaster.pid 读取 PID
        postmaster_pid_file = self.data_dir / "postmaster.pid"
        if postmaster_pid_file.exists():
            try:
                with open(postmaster_pid_file, "r") as f:
                    pid = int(f.readline().strip())
                with open(self.pid_file, "w") as f:
                    f.write(str(pid))
            except Exception as e:
                print(f"⚠️ 保存 PID 失败: {e}")
    
    def _wait_for_ready(self, timeout: int = 30) -> bool:
        """等待数据库就绪"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # 尝试连接
                result = subprocess.run(
                    [str(self.psql), "-p", str(self.port), "-U", self.username, 
                     "-h", "127.0.0.1", "-c", "SELECT 1"],
                    capture_output=True,
                    text=True,
                    env={**os.environ, "PGPASSWORD": self.password},
                    cwd=str(self.pg_bin_dir)
                )
                if result.returncode == 0:
                    return True
            except Exception:
                pass
            
            time.sleep(0.5)
        
        return False
    
    def _create_database(self):
        """创建应用数据库"""
        # 先检查数据库是否存在
        result = subprocess.run(
            [str(self.psql), "-p", str(self.port), "-U", self.username,
             "-h", "127.0.0.1", "-c", f"SELECT 1 FROM pg_database WHERE datname = '{self.database}'"],
            capture_output=True,
            text=True,
            env={**os.environ, "PGPASSWORD": self.password},
            cwd=str(self.pg_bin_dir)
        )
        
        if self.database not in result.stdout:
            print(f"🔄 创建数据库: {self.database}")
            subprocess.run(
                [str(self.psql), "-p", str(self.port), "-U", self.username,
                 "-h", "127.0.0.1", "-c", f"CREATE DATABASE {self.database}"],
                capture_output=True,
                env={**os.environ, "PGPASSWORD": self.password},
                cwd=str(self.pg_bin_dir)
            )
            
            # 启用 pgvector 扩展
            init_sql = self.base_dir / "init.sql"
            if init_sql.exists():
                print("🔄 执行初始化 SQL...")
                subprocess.run(
                    [str(self.psql), "-p", str(self.port), "-U", self.username,
                     "-h", "127.0.0.1", "-d", self.database, "-f", str(init_sql)],
                    capture_output=True,
                    env={**os.environ, "PGPASSWORD": self.password},
                    cwd=str(self.pg_bin_dir)
                )
    
    def stop(self):
        """停止 PostgreSQL 服务 - 使用 pg_ctl 命令"""
        print("🛑 正在停止 PostgreSQL...")
        
        try:
            # 使用 pg_ctl stop 命令
            # 命令格式: ./pg_ctl stop -D "../data"
            cmd = [
                str(self.pg_ctl),
                "stop",
                "-D", str(self.data_dir),
                "-m", "fast"  # fast 模式，立即断开连接
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.pg_bin_dir),
                timeout=10
            )
            
            if result.returncode == 0:
                print("✅ PostgreSQL 已停止")
            else:
                print(f"⚠️ 停止命令输出: {result.stderr}")
                # 如果 pg_ctl 失败，尝试强制终止
                self._force_stop()
            
        except subprocess.TimeoutExpired:
            print("⚠️ 停止超时，强制终止")
            self._force_stop()
        except Exception as e:
            print(f"⚠️ 停止时出错: {e}")
            self._force_stop()
        
        # 清理 PID 文件
        if self.pid_file.exists():
            self.pid_file.unlink()
    
    def _force_stop(self):
        """强制停止 PostgreSQL"""
        # 尝试从 PID 文件终止
        if self.pid_file.exists():
            try:
                with open(self.pid_file, "r") as f:
                    pid = int(f.read().strip())
                
                if self.platform == "Windows":
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                else:
                    os.kill(pid, signal.SIGKILL)
                print("✅ 已强制终止 PostgreSQL 进程")
            except Exception as e:
                print(f"⚠️ 强制终止失败: {e}")
    
    def restart(self) -> bool:
        """重启 PostgreSQL 服务"""
        print("🔄 正在重启 PostgreSQL...")
        self.stop()
        time.sleep(1)
        return self.start()
    
    def get_connection_url(self) -> str:
        """获取数据库连接 URL"""
        return f"postgresql+asyncpg://{self.username}:{self.password}@127.0.0.1:{self.port}/{self.database}"


# 全局管理器实例
_postgres_manager: Optional[PostgresManager] = None


def get_postgres_manager() -> PostgresManager:
    """获取 PostgreSQL 管理器实例"""
    global _postgres_manager
    if _postgres_manager is None:
        _postgres_manager = PostgresManager()
    return _postgres_manager
