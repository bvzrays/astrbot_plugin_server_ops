import asyncssh
import asyncio
from typing import Tuple, Optional

class AsyncSSHManager:
    """
    异步 SSH 管理器，核心连接逻辑完全同步自 astrbot_plugin_ssh。
    """
    def __init__(self, host: str, port: int, username: str, 
                 password: Optional[str] = None, 
                 key_path: Optional[str] = None,
                 passphrase: Optional[str] = None,
                 default_timeout: int = 30,
                 output_max_chars: int = 3000):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_path = key_path
        self.passphrase = passphrase
        self.default_timeout = default_timeout
        self.output_max_chars = output_max_chars
        self._conn = None
        self._lock = asyncio.Lock()

    async def _get_conn(self):
        """同步 ssh 插件的 connect 调用方式：在锁外连接以支持并发，在锁内检查状态"""
        from astrbot.api import logger
        
        # 1. 快速路径：检查现有连接
        async with self._lock:
            if self._conn and not self._conn.is_closing():
                return self._conn
        
        # 2. 慢速路径：在锁外连接（参照 ssh 插件逻辑，避免阻塞事件循环）
        logger.info(f"SSHManager: 正在连接 {self.username}@{self.host}:{self.port} ...")
        
        known_hosts = None # 对应 ssh 插件的 known_hosts_path 为空时的逻辑
        
        try:
            # 严格按照 ssh 插件的 positional host + kwargs 方式
            new_conn = await asyncssh.connect(
                self.host,
                port=self.port,
                username=self.username,
                password=self.password if not self.key_path else None,
                client_keys=[self.key_path] if (self.key_path and self.key_path.strip()) else None,
                passphrase=self.passphrase if (self.key_path and self.key_path.strip() and self.passphrase) else None,
                known_hosts=known_hosts,
                login_timeout=60 # 保持 60s 以应对公网环境，比 ssh 插件默认的 10s 更稳
            )
            
            # 3. 结果存储与二次检查
            async with self._lock:
                if self._conn and not self._conn.is_closing():
                    # 并发任务已经创建了连接，关闭当前的，返回已存的
                    new_conn.close()
                    return self._conn
                self._conn = new_conn
                logger.info(f"SSHManager: 成功连接至 {self.host}")
                return self._conn
                
        except Exception as e:
            logger.error(f"SSHManager: 连接失败: {str(e)}")
            raise

    def _truncate_output(self, text: str) -> str:
        if not text: return ""
        if len(text) > self.output_max_chars:
            return text[:self.output_max_chars] + f"\n...(由于长度限制已截断)"
        return text

    async def execute_command(self, command: str, timeout: Optional[int] = None) -> Tuple[int, str, str]:
        """执行命令"""
        exec_timeout = timeout if timeout is not None else self.default_timeout
        try:
            conn = await self._get_conn()
            result = await asyncio.wait_for(conn.run(command), timeout=exec_timeout)
            return result.exit_status, self._truncate_output(result.stdout), self._truncate_output(result.stderr)
        except Exception as e:
            if isinstance(e, asyncssh.ConnectionLost): self._conn = None
            return -1, "", str(e)

    async def execute_install(self, command: str, timeout: int = 600) -> Tuple[int, str, str]:
        """包安装专供逻辑"""
        wrapped_command = f'DEBIAN_FRONTEND=noninteractive {command}'
        for pkg_mgr in ['apt-get install', 'apt install', 'yum install', 'dnf install']:
            if pkg_mgr in wrapped_command and '-y' not in wrapped_command:
                wrapped_command = wrapped_command.replace(pkg_mgr, f'{pkg_mgr} -y')

        try:
            conn = await self._get_conn()
            result = await asyncio.wait_for(conn.run(wrapped_command, term_type='xterm'), timeout=timeout)
            return result.exit_status, self._truncate_output(result.stdout), self._truncate_output(result.stderr)
        except Exception as e:
            if isinstance(e, asyncssh.ConnectionLost): self._conn = None
            return -1, "", str(e)

    async def read_file(self, filepath: str) -> str:
        """读取远端文件内容"""
        try:
            conn = await self._get_conn()
            result = await asyncio.wait_for(conn.run(f'cat "{filepath}"'), timeout=self.default_timeout)
            if result.exit_status != 0:
                return f"Error: {result.stderr or 'File not found'}"
            return self._truncate_output(result.stdout)
        except Exception as e:
            if isinstance(e, asyncssh.ConnectionLost): self._conn = None
            return f"SSH Read Error: {str(e)}"

    async def write_file(self, filepath: str, content: str) -> str:
        """安全写入远端文件"""
        try:
            conn = await self._get_conn()
            cmd = f"mkdir -p \"$(dirname '{filepath}')\" && cat > '{filepath}' << 'HEREDOC_EOF'\n{content}\nHEREDOC_EOF"
            result = await asyncio.wait_for(conn.run(cmd), timeout=self.default_timeout)
            if result.exit_status != 0:
                return f"Error: {result.stderr}"
            return f"Successfully written to '{filepath}'"
        except Exception as e:
            if isinstance(e, asyncssh.ConnectionLost): self._conn = None
            return f"SSH Write Error: {str(e)}"
