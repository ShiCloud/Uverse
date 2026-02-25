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
        self._load_config()
    
    def _load_config(self):
        """从环境变量加载配置 - 支持重新加载"""
        # 从环境变量读取 PostgreSQL 目录，默认为相对路径
        pg_dir_env = os.getenv("POSTGRES_DIR", "postgres")
        print(f"[PostgresManager] 从环境变量读取 POSTGRES_DIR: {pg_dir_env}")
        
        if os.path.isabs(pg_dir_env):
            self.pg_dir = Path(pg_dir_env)
        else:
            # 相对路径，基于 backend 目录
            self.pg_dir = self.base_dir / pg_dir_env
        
        # 确保 bin 目录是从 pg_dir 拼接的
        self.pg_bin_dir = self.pg_dir / "bin"
        self.data_dir = self.pg_dir / "data"
        self.log_file = self.pg_dir / "postgres.log"
        self.pid_file = self.pg_dir / "postgres.pid"
        self.process: Optional[subprocess.Popen] = None
        
        print(f"[PostgresManager] pg_dir: {self.pg_dir}")
        print(f"[PostgresManager] pg_bin_dir: {self.pg_bin_dir}")
        
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
        self.port = int(os.getenv("DATABASE_PORT", "15432"))
        self.username = os.getenv("DATABASE_USER", "postgres")
        self.password = os.getenv("DATABASE_PASSWORD", "postgres")
        self.database = os.getenv("DATABASE_NAME", "knowledge_base")
        
        print(f"[PostgresManager] 配置加载完成: port={self.port}, database={self.database}")
    
    def reload_config(self):
        """重新加载配置 - 在环境变量更新后调用"""
        print("[PostgresManager] 重新加载配置...")
        self._load_config()
        
    def is_installed(self) -> bool:
        """检查 PostgreSQL 便携版是否已安装"""
        return self.pg_ctl.exists() and self.initdb.exists()
    
    def is_initialized(self) -> bool:
        """检查数据库是否已初始化"""
        pg_version_file = self.data_dir / "PG_VERSION"
        is_init = self.data_dir.exists() and pg_version_file.exists()
        print(f"[DB] 检查初始化: data_dir={self.data_dir}, 存在={self.data_dir.exists()}, PG_VERSION={pg_version_file.exists()}, 结果={is_init}")
        return is_init
    
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
            print(f"[ERROR] PostgreSQL 便携版未找到: {self.pg_dir}")
            return False
        
        if self.is_initialized():
            print("[OK] 数据库已初始化")
            return True
        
        print("[RESTART] 正在初始化 PostgreSQL 数据库...")
        print(f"[DB] initdb: {self.initdb}")
        print(f"[DB] data_dir: {self.data_dir}")
        
        # 创建数据目录
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            print(f"[DB] 数据目录创建完成: {self.data_dir}")
        except Exception as e:
            print(f"[ERROR] 创建数据目录失败: {e}")
            return False
        
        # Windows: 检查目录是否可写
        if self.platform == "Windows":
            test_file = self.data_dir / ".write_test"
            try:
                test_file.write_text("test")
                test_file.unlink()
                print("[OK] 数据目录可写")
            except Exception as e:
                print(f"[ERROR] 数据目录不可写: {e}")
                print("[HINT] 请检查目录权限或以管理员身份运行")
                return False
        
        # 运行 initdb - 使用与 PostgreSQL 相同的环境变量
        env = self._get_pg_env()
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
        
        print(f"[DB] 执行 initdb: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(self.pg_bin_dir)
            )
            
            print(f"[DB] initdb 返回码: {result.returncode}")
            if result.stdout:
                print(f"[DB] initdb 输出: {result.stdout[:500]}")  # 限制输出长度
            if result.stderr:
                print(f"[DB] initdb 错误: {result.stderr}")
            
            if result.returncode != 0:
                print(f"[ERROR] 初始化失败: {result.stderr}")
                return False
            
            # 设置密码 - 修改 pg_hba.conf 允许本地信任连接
            self._setup_hba_conf()
            
            print("[OK] 数据库初始化完成")
            return True
            
        except Exception as e:
            print(f"[ERROR] 初始化异常: {e}")
            import traceback
            traceback.print_exc()
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
        print("[OK] 已配置 pg_hba.conf")
    
    def _setup_postgresql_conf(self):
        """设置 postgresql.conf 配置端口 - Windows 优化版本"""
        conf_file = self.data_dir / "postgresql.conf"
        
        # 读取现有配置
        if conf_file.exists():
            with open(conf_file, "r") as f:
                lines = f.readlines()
        else:
            lines = []
        
        # 基础配置
        port_config = f"port = {self.port}\n"
        listen_config = "listen_addresses = '127.0.0.1,localhost'\n"
        max_conn_config = "max_connections = 100\n"
        
        # Windows 关键修复: 禁用并行查询 worker，避免 0xC0000142 错误
        # 参考: https://www.postgresql.org/message-id/202408211721.diphtrjwwjf4%40alvherre.pgsql
        windows_fixes = [
            "\n# Windows DLL 错误修复 (0xC0000142)\n",
            "max_parallel_workers = 0\n",
            "max_parallel_workers_per_gather = 0\n",
            "max_parallel_maintenance_workers = 0\n",
            "max_worker_processes = 8\n",
            "# 禁用可能导致问题的后台进程\n",
            "autovacuum = on\n",
            "autovacuum_max_workers = 2\n",
        ]
        
        # 检查是否已有配置
        has_port = False
        has_listen = False
        has_max_conn = False
        has_windows_fix = False
        
        for i, line in enumerate(lines):
            if line.strip().startswith("port ="):
                lines[i] = port_config
                has_port = True
            if line.strip().startswith("listen_addresses ="):
                lines[i] = listen_config
                has_listen = True
            if line.strip().startswith("max_connections ="):
                has_max_conn = True
            if "Windows DLL 错误修复" in line:
                has_windows_fix = True
        
        additions = []
        if not has_port:
            additions.append(f"\n# Custom port setting\n{port_config}")
        if not has_listen:
            additions.append(f"\n# Custom listen_addresses setting\n{listen_config}")
        if not has_max_conn:
            additions.append(f"\n# Connection settings\n{max_conn_config}")
        
        # 添加 Windows 修复配置
        if not has_windows_fix and self.platform == "Windows":
            additions.extend(windows_fixes)
            print("[DB] 添加 Windows DLL 修复配置 (禁用并行 worker)")
        
        if additions:
            lines.append("\n# Uverse Auto Configuration\n")
            lines.extend(additions)
        
        with open(conf_file, "w") as f:
            f.writelines(lines)
        
        print(f"[OK] 已配置 postgresql.conf (端口: {self.port})")
    
    def start(self) -> bool:
        """启动 PostgreSQL 服务 - 使用 pg_ctl 命令（带详细计时）"""
        import time
        total_start = time.time()
        
        print(f"[DB] 开始启动 PostgreSQL...")
        print(f"[DB] pg_ctl: {self.pg_ctl}")
        print(f"[DB] data_dir: {self.data_dir}")
        print(f"[DB] 端口: {self.port}")
        
        # 1. 检查安装
        t1 = time.time()
        if not self.is_installed():
            print(f"[WARN] PostgreSQL 可执行文件不存在: pg_ctl={self.pg_ctl}, initdb={self.initdb}")
            return False
        print(f"[DB] [计时] 检查安装: {(time.time()-t1)*1000:.1f}ms")
        
        # 2. 检查是否已运行
        t2 = time.time()
        if self.is_running():
            print("[OK] PostgreSQL 已在运行")
            return True
        print(f"[DB] [计时] 检查运行状态: {(time.time()-t2)*1000:.1f}ms")
        
        # 3. 检查数据目录
        t3 = time.time()
        if not self.is_initialized():
            print(f"[DB] 数据目录未初始化，开始初始化...")
            if not self.init_database():
                return False
        else:
            print(f"[DB] 数据目录已初始化")
        print(f"[DB] [计时] 检查/初始化数据目录: {(time.time()-t3)*1000:.1f}ms")
        
        # 4. 配置 postgresql.conf
        t4 = time.time()
        self._setup_postgresql_conf()
        print(f"[DB] [计时] 配置 postgresql.conf: {(time.time()-t4)*1000:.1f}ms")
        
        print("[START] 正在启动 PostgreSQL...")
        
        # 使用 pg_ctl start 命令启动
        # 命令格式: ./pg_ctl start -D "../data" -l logfile
        log_file_path = self.pg_dir / "logfile"
        
        cmd = [
            str(self.pg_ctl),
            "start",
            "-D", str(self.data_dir),
            "-l", str(log_file_path)
        ]
        
        print(f"[DB] 执行命令: {' '.join(cmd)}")
        
        # Windows 关键: 设置环境变量确保子进程能找到 DLL
        # 参考: https://www.postgresql.org/message-id/202408211721.diphtrjwwjf4%40alvherre.pgsql
        env = os.environ.copy()
        if self.platform == "Windows":
            # 将 PostgreSQL bin 目录添加到 PATH 最前面
            current_path = env.get('PATH', '')
            if str(self.pg_bin_dir) not in current_path:
                env['PATH'] = str(self.pg_bin_dir) + os.pathsep + current_path
                print(f"[DB] 更新 PATH: {self.pg_bin_dir}")
            
            # 设置 PGROOT 帮助某些扩展找到安装目录
            env['PGROOT'] = str(self.pg_dir)
            env['PGDATA'] = str(self.data_dir)
        
        # Windows: pg_ctl start 会阻塞，使用 Popen 不等待，直接检查就绪状态
        try:
            pgctl_start = time.time()
            print(f"[DB] 执行 pg_ctl start (不等待)...")
            
            # 使用 Popen 启动但不等待完成 - pg_ctl start 在 Windows 上不会返回
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.pg_bin_dir),
                env=env,
                # Windows 上防止显示控制台窗口
                creationflags=0x08000000 if self.platform == "Windows" else 0  # CREATE_NO_WINDOW
            )
            
            # 不调用 communicate()，让 pg_ctl 在后台运行
            # 等待一小段时间让启动命令发送给 PostgreSQL
            time.sleep(0.5)
            
            print(f"[DB] [计时] pg_ctl start 发送命令: {(time.time() - pgctl_start)*1000:.1f}ms")
            
            # 5. 等待数据库就绪（最耗时的步骤）
            t5 = time.time()
            print("[DB] 等待数据库就绪（最长 60 秒）...")
            if not self._wait_for_ready(timeout=60):
                print("[ERROR] PostgreSQL 启动超时（60秒）")
                
                # 自动修复：如果等待超时，可能是数据目录损坏，尝试重置
                print("[DB] 尝试自动修复：数据目录可能损坏，准备重置...")
                self.stop()
                time.sleep(2)
                
                if self._auto_reset_data_dir():
                    print("[DB] 自动修复完成，重新启动...")
                    # 重新尝试启动（只递归一次）
                    return self._retry_start()
                else:
                    print("[ERROR] 自动修复失败")
                    return False
            
            # 6. 创建应用数据库
            t6 = time.time()
            print("[DB] 数据库已就绪，创建应用数据库...")
            if not self._create_database():
                print("[ERROR] 创建应用数据库失败")
                return False
            print(f"[DB] [计时] 创建应用数据库: {(time.time()-t6)*1000:.1f}ms")
            
            # 7. 保存 PID
            t7 = time.time()
            self._save_pid()
            print(f"[DB] [计时] 保存 PID: {(time.time()-t7)*1000:.1f}ms")
            
            # 注册退出时的清理函数
            atexit.register(self.stop)
            
            total_elapsed = time.time() - total_start
            print(f"[OK] PostgreSQL 已启动 (端口: {self.port}, 总耗时: {total_elapsed:.2f}s)")
            return True
            
        except Exception as e:
            print(f"[ERROR] 启动失败: {e}")
            import traceback
            traceback.print_exc()
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
                print(f"[WARN] 保存 PID 失败: {e}")
    
    def _get_pg_env(self) -> dict:
        """获取 PostgreSQL 执行环境变量"""
        env = os.environ.copy()
        env["PGPASSWORD"] = self.password
        
        if self.platform == "Windows":
            # 确保 PATH 包含 PostgreSQL bin 目录
            current_path = env.get('PATH', '')
            if str(self.pg_bin_dir) not in current_path:
                env['PATH'] = str(self.pg_bin_dir) + os.pathsep + current_path
            env['PGROOT'] = str(self.pg_dir)
            env['PGDATA'] = str(self.data_dir)
        
        return env
    
    def _wait_for_ready(self, timeout: int = 60) -> bool:
        """等待数据库就绪 - Windows 优化版本（延长超时，带详细计时）"""
        import time
        start_time = time.time()
        check_interval = 0.5
        
        print(f"[DB] 等待数据库就绪，超时: {timeout}s, psql: {self.psql}")
        print(f"[DB] 首次连接尝试中...")
        
        attempt = 0
        last_error = None
        pg_env = self._get_pg_env()
        first_success_time = None
        
        while time.time() - start_time < timeout:
            attempt += 1
            loop_start = time.time()
            
            # 先检查进程是否还在运行
            if not self.is_running():
                print(f"[ERROR] PostgreSQL 进程已退出 (尝试 {attempt})")
                self._print_postgres_log()
                return False
            
            try:
                # 尝试连接
                for host in ["127.0.0.1", "localhost"]:
                    conn_start = time.time()
                    result = subprocess.run(
                        [str(self.psql), "-p", str(self.port), "-U", self.username, 
                         "-h", host, "-c", "SELECT 1"],
                        capture_output=True,
                        text=True,
                        env=pg_env,
                        cwd=str(self.pg_bin_dir),
                        timeout=5
                    )
                    conn_elapsed = time.time() - conn_start
                    
                    if result.returncode == 0:
                        total_elapsed = time.time() - start_time
                        if first_success_time is None:
                            first_success_time = total_elapsed
                            print(f"[DB] 首次连接成功！耗时: {first_success_time:.2f}s")
                        print(f"[DB] 数据库就绪 (总等待 {total_elapsed:.2f}s, 尝试 {attempt} 次, host={host}, 单次连接 {conn_elapsed*1000:.1f}ms)")
                        return True
                    else:
                        last_error = result.stderr.strip()[:50] if result.stderr else f"返回码: {result.returncode}"
                        
            except subprocess.TimeoutExpired:
                last_error = "连接超时"
            except Exception as e:
                last_error = str(e)[:50]
            
            # 每10秒输出一次进度
            elapsed = time.time() - start_time
            if attempt % 20 == 0:
                print(f"[DB] 等待中... (已等待 {elapsed:.1f}s, 尝试 {attempt} 次)")
            
            # 确保每次循环至少等待 check_interval
            loop_elapsed = time.time() - loop_start
            if loop_elapsed < check_interval:
                time.sleep(check_interval - loop_elapsed)
        
        print(f"[ERROR] 数据库启动超时，共尝试 {attempt} 次")
        print(f"[ERROR] 最后错误: {last_error}")
        self._print_postgres_log()
        return False
    
    def _print_postgres_log(self):
        """打印 PostgreSQL 日志文件内容，帮助诊断问题"""
        log_file_path = self.pg_dir / "logfile"
        if log_file_path.exists():
            try:
                with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if content:
                        print("[DB] PostgreSQL 日志内容:")
                        # 只打印最后 20 行
                        lines = content.strip().split('\n')
                        for line in lines[-20:]:
                            print(f"  {line}")
                    else:
                        print("[DB] PostgreSQL 日志文件为空")
            except Exception as e:
                print(f"[DB] 读取日志文件失败: {e}")
        else:
            print(f"[DB] 日志文件不存在: {log_file_path}")
    
    def _create_database(self) -> bool:
        """创建应用数据库"""
        print(f"[DB] 检查应用数据库是否存在: {self.database}")
        
        pg_env = self._get_pg_env()
        
        # 先检查数据库是否存在 - 使用 -t 获取简洁输出，-A 去除对齐
        result = subprocess.run(
            [str(self.psql), "-p", str(self.port), "-U", self.username,
             "-h", "127.0.0.1", "-t", "-A", "-c", 
             f"SELECT COUNT(*) FROM pg_database WHERE datname = '{self.database}'"],
            capture_output=True,
            text=True,
            env=pg_env,
            cwd=str(self.pg_bin_dir),
            timeout=15
        )
        
        if result.returncode != 0:
            print(f"[WARN] 检查数据库存在性失败: {result.stderr}")
            return False
        
        # 检查输出是否包含 "1"（表示数据库存在）
        output = result.stdout.strip()
        if output == "1":
            print(f"[OK] 数据库 {self.database} 已存在")
            return True
        
        # 数据库不存在，创建它
        print(f"[RESTART] 创建数据库: {self.database}")
        create_result = subprocess.run(
            [str(self.psql), "-p", str(self.port), "-U", self.username,
             "-h", "127.0.0.1", "-c", f"CREATE DATABASE {self.database}"],
            capture_output=True,
            text=True,
            env=pg_env,
            cwd=str(self.pg_bin_dir),
            timeout=60
        )
        
        if create_result.returncode != 0:
            # 检查是否是因为数据库已存在（可能是竞态条件）
            if "already exists" in create_result.stderr.lower():
                print(f"[OK] 数据库 {self.database} 已存在（创建时检测到）")
                return True
            print(f"[ERROR] 创建数据库失败: {create_result.stderr}")
            return False
        
        print(f"[OK] 数据库 {self.database} 创建成功")
        
        # 启用 pgvector 扩展
        init_sql = self.base_dir / "init.sql"
        if init_sql.exists():
            print("[RESTART] 执行初始化 SQL...")
            init_result = subprocess.run(
                [str(self.psql), "-p", str(self.port), "-U", self.username,
                 "-h", "127.0.0.1", "-d", self.database, "-f", str(init_sql)],
                capture_output=True,
                text=True,
                env=pg_env,
                cwd=str(self.pg_bin_dir),
                timeout=60
            )
            if init_result.returncode != 0:
                print(f"[WARN] 执行初始化 SQL 失败: {init_result.stderr}")
            else:
                print("[OK] 初始化 SQL 执行成功")
        
        return True
    
    def stop(self):
        """停止 PostgreSQL 服务 - 使用 pg_ctl 命令"""
        print("[STOP] 正在停止 PostgreSQL...")
        
        # 首先检查是否真的在运行
        if not self.is_running():
            print("[OK] PostgreSQL 未在运行")
            # 清理可能残留的 PID 文件
            if self.pid_file.exists():
                self.pid_file.unlink()
            return
        
        try:
            # Windows: pg_ctl stop 可能卡住，使用短超时
            timeout = 5 if self.platform == "Windows" else 20
            
            # 使用 pg_ctl stop 命令
            cmd = [
                str(self.pg_ctl),
                "stop",
                "-D", str(self.data_dir),
                "-m", "fast"  # fast 模式，立即断开连接
            ]
            
            env = self._get_pg_env()
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.pg_bin_dir),
                timeout=timeout,
                env=env
            )
            
            if result.returncode == 0:
                print("[OK] PostgreSQL 已停止")
            else:
                stderr = result.stderr.strip() if result.stderr else ""
                # 如果已经停止，不算错误
                if "not running" in stderr.lower() or "no server running" in stderr.lower():
                    print("[OK] PostgreSQL 未在运行")
                else:
                    print(f"[WARN] pg_ctl stop 返回: {stderr}")
                    self._force_stop()
            
        except subprocess.TimeoutExpired:
            print("[WARN] pg_ctl stop 超时，使用强制终止")
            self._force_stop()
        except Exception as e:
            print(f"[WARN] 停止时出错: {e}")
            self._force_stop()
        
        # 清理 PID 文件
        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
            except Exception:
                pass
    
    def _force_stop(self):
        """强制停止 PostgreSQL - 确保所有进程都被终止"""
        print("[STOP] 强制停止 PostgreSQL...")
        
        if self.platform == "Windows":
            # Windows: 终止所有 postgres 进程
            try:
                # 方法1: 按进程名终止所有 postgres.exe
                result = subprocess.run(
                    ["taskkill", "/F", "/IM", "postgres.exe"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    print("[OK] 已终止所有 PostgreSQL 进程")
                else:
                    # 方法2: 如果按名称失败，尝试从 PID 文件终止进程树
                    if self.pid_file.exists():
                        try:
                            with open(self.pid_file, "r") as f:
                                pid = int(f.read().strip())
                            subprocess.run(
                                ["taskkill", "/F", "/T", "/PID", str(pid)],
                                capture_output=True
                            )
                            print("[OK] 已终止 PostgreSQL 进程树")
                        except Exception as e:
                            print(f"[WARN] 终止进程树失败: {e}")
            except Exception as e:
                print(f"[WARN] 强制终止失败: {e}")
        else:
            # Linux/Mac: 使用 kill 终止主进程
            if self.pid_file.exists():
                try:
                    with open(self.pid_file, "r") as f:
                        pid = int(f.read().strip())
                    os.kill(pid, signal.SIGKILL)
                    print("[OK] 已强制终止 PostgreSQL 进程")
                except Exception as e:
                    print(f"[WARN] 强制终止失败: {e}")
    
    def _auto_reset_data_dir(self) -> bool:
        """自动重置数据目录（用于修复启动失败）"""
        import shutil
        import time
        
        print("[AUTO-FIX] 自动重置 PostgreSQL 数据目录...")
        
        if not self.data_dir.exists():
            print("[AUTO-FIX] 数据目录不存在，直接初始化")
            return self.init_database()
        
        # 备份旧目录
        backup_dir = self.data_dir.parent / f"data_backup_{int(time.time())}"
        try:
            print(f"[AUTO-FIX] 备份旧数据目录到: {backup_dir}")
            shutil.move(str(self.data_dir), str(backup_dir))
            print("[AUTO-FIX] 备份完成")
        except Exception as e:
            print(f"[AUTO-FIX] 备份失败: {e}")
            # 尝试直接删除
            try:
                shutil.rmtree(str(self.data_dir))
                print("[AUTO-FIX] 已删除旧数据目录")
            except Exception as e2:
                print(f"[AUTO-FIX] 删除也失败: {e2}")
                return False
        
        # 重新初始化
        time.sleep(1)
        return self.init_database()
    
    def _retry_start(self) -> bool:
        """重新尝试启动（用于自动修复后）"""
        print("[RETRY] 重新尝试启动 PostgreSQL...")
        
        # 重新配置
        self._setup_postgresql_conf()
        
        log_file_path = self.pg_dir / "logfile"
        cmd = [
            str(self.pg_ctl),
            "start",
            "-D", str(self.data_dir),
            "-l", str(log_file_path)
        ]
        
        env = self._get_pg_env()
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                   cwd=str(self.pg_bin_dir), env=env)
            
            if result.returncode != 0:
                print(f"[RETRY] 重新启动失败: {result.stderr}")
                return False
            
            # 等待就绪（缩短超时，因为已经重置了）
            print("[RETRY] 等待数据库就绪...")
            if not self._wait_for_ready(timeout=45):
                print("[RETRY] 等待超时")
                return False
            
            # 创建应用数据库
            if not self._create_database():
                return False
            
            self._save_pid()
            atexit.register(self.stop)
            
            print("[RETRY] PostgreSQL 启动成功（自动修复后）")
            return True
            
        except Exception as e:
            print(f"[RETRY] 异常: {e}")
            return False
    
    def restart(self) -> bool:
        """重启 PostgreSQL 服务"""
        print("[RESTART] 正在重启 PostgreSQL...")
        self.stop()
        time.sleep(1)
        return self.start()
    
    def diagnose(self) -> dict:
        """诊断 PostgreSQL 状态和常见问题"""
        print("\n[DIAGNOSE] 开始诊断 PostgreSQL...")
        
        results = {
            "installed": False,
            "initialized": False,
            "running": False,
            "port_available": True,
            "data_dir_writable": False,
            "has_dll_error": False,
            "errors": []
        }
        
        # 1. 检查是否安装
        results["installed"] = self.is_installed()
        if not results["installed"]:
            results["errors"].append(f"PostgreSQL 未安装或路径错误: {self.pg_dir}")
        
        # 2. 检查是否初始化
        results["initialized"] = self.is_initialized()
        if results["installed"] and not results["initialized"]:
            results["errors"].append("数据目录未初始化")
        
        # 3. 检查是否运行
        results["running"] = self.is_running()
        
        # 4. 检查端口是否被占用
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('127.0.0.1', self.port))
                if result == 0:
                    results["port_available"] = False
                    if not results["running"]:
                        results["errors"].append(f"端口 {self.port} 被其他程序占用")
        except Exception as e:
            results["errors"].append(f"端口检查失败: {e}")
        
        # 5. 检查数据目录是否可写
        if self.data_dir.exists():
            test_file = self.data_dir / ".write_test"
            try:
                test_file.write_text("test")
                test_file.unlink()
                results["data_dir_writable"] = True
            except Exception as e:
                results["errors"].append(f"数据目录不可写: {e}")
        
        # 6. 检查日志文件
        log_file = self.pg_dir / "logfile"
        if log_file.exists():
            try:
                content = log_file.read_text(errors='ignore')
                # 查找常见错误
                if "could not bind" in content:
                    results["errors"].append("端口绑定失败，可能被占用")
                if "Permission denied" in content:
                    results["errors"].append("权限被拒绝，请检查目录权限")
                if "lock file" in content and "already in use" in content:
                    results["errors"].append("数据目录被锁定，可能已有实例运行")
                # 检测 0xC0000142 DLL 初始化错误
                if "0xC0000142" in content:
                    results["has_dll_error"] = True
                    results["errors"].append("检测到 Windows DLL 初始化错误 (0xC0000142)")
                    results["errors"].append("可能原因: 1) 缺少 VC++ 运行时库 2) PATH 环境变量问题 3) 数据目录损坏")
                    results["errors"].append("解决方案: 1) 安装 VC++ Redistributable 2) 删除 data 目录后重启")
            except Exception:
                pass
        
        # 打印诊断结果
        print(f"[DIAGNOSE] 安装: {'✓' if results['installed'] else '✗'}")
        print(f"[DIAGNOSE] 初始化: {'✓' if results['initialized'] else '✗'}")
        print(f"[DIAGNOSE] 运行中: {'✓' if results['running'] else '✗'}")
        print(f"[DIAGNOSE] 端口可用: {'✓' if results['port_available'] else '✗'}")
        print(f"[DIAGNOSE] 目录可写: {'✓' if results['data_dir_writable'] else '✗'}")
        print(f"[DIAGNOSE] DLL错误: {'✓' if results['has_dll_error'] else '✗'}")
        
        if results["errors"]:
            print("[DIAGNOSE] 发现的问题:")
            for error in results["errors"]:
                print(f"  - {error}")
        
        print()
        return results
    
    def reset_data_dir(self) -> bool:
        """重置数据目录（谨慎使用！会删除所有数据）"""
        print("[WARNING] 即将重置 PostgreSQL 数据目录！")
        print(f"[WARNING] 数据目录: {self.data_dir}")
        print("[WARNING] 这将删除所有数据库数据！")
        
        # 先停止服务
        self.stop()
        time.sleep(1)
        
        # 备份旧目录
        if self.data_dir.exists():
            import shutil
            backup_dir = self.data_dir.parent / f"data_backup_{int(time.time())}"
            try:
                shutil.move(str(self.data_dir), str(backup_dir))
                print(f"[OK] 旧数据目录已备份到: {backup_dir}")
            except Exception as e:
                print(f"[ERROR] 备份失败: {e}")
                return False
        
        # 重新初始化
        return self.init_database()
    
    def get_connection_url(self) -> str:
        """获取数据库连接 URL"""
        return f"postgresql+asyncpg://{self.username}:{self.password}@127.0.0.1:{self.port}/{self.database}"


# 全局管理器实例
_postgres_manager: Optional[PostgresManager] = None


def get_postgres_manager(reload: bool = False) -> PostgresManager:
    """
    获取 PostgreSQL 管理器实例
    
    Args:
        reload: 如果为 True，强制重新加载配置（用于配置更新后）
    """
    global _postgres_manager
    if _postgres_manager is None:
        _postgres_manager = PostgresManager()
    elif reload:
        # 重新加载环境变量配置
        _postgres_manager.reload_config()
    return _postgres_manager
