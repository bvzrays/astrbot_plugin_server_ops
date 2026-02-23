import asyncssh
import asyncio
from typing import Tuple, Optional

# -----------------------------------------------------------------------------------
# 宽容算法集合：覆盖新旧服务器常用的 kex / 加密 / MAC / 主机密钥算法。
# asyncssh 默认只协商「现代」算法，若服务器（尤其公网复用型）只支持旧算法，
# 握手阶段会立即收到 Connection lost / Disconnect，这套参数可消除该问题。
# -----------------------------------------------------------------------------------
_COMPAT_ALGS = dict(
    kex_algs=[
        # 首选现代 ECDH / Curve25519
        "curve25519-sha256",
        "curve25519-sha256@libssh.org",
        "ecdh-sha2-nistp521",
        "ecdh-sha2-nistp384",
        "ecdh-sha2-nistp256",
        # 旧式 DH（部分公网服务器仍然使用）
        "diffie-hellman-group-exchange-sha256",
        "diffie-hellman-group14-sha256",
        "diffie-hellman-group14-sha1",
        "diffie-hellman-group1-sha1",
    ],
    encryption_algs=[
        "aes128-ctr", "aes192-ctr", "aes256-ctr",
        "aes128-cbc", "aes192-cbc", "aes256-cbc",
        "3des-cbc",
        "aes128-gcm@openssh.com", "aes256-gcm@openssh.com",
        "chacha20-poly1305@openssh.com",
    ],
    mac_algs=[
        "hmac-sha2-256", "hmac-sha2-512",
        "hmac-sha1", "hmac-md5",
        "hmac-sha2-256-etm@openssh.com", "hmac-sha2-512-etm@openssh.com",
    ],
    server_host_key_algs=[
        "ssh-rsa", "rsa-sha2-256", "rsa-sha2-512",
        "ssh-ed25519", "ecdsa-sha2-nistp256",
        "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
        "ssh-dss",
    ],
)


class AsyncSSHManager:
    """
    异步 SSH 管理器。

    修复要点 (v2.0)：
    1. 加入宽容算法集合，兼容新旧服务器，避免 'Connection lost' 握手失败。
    2. 连接失败时捕获完整异常类型并记录，便于诊断。
    3. execute_command / execute_install 在 ConnectionLost 时自动重置连接，
       下次调用可自动重连。
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: Optional[str] = None,
        key_path: Optional[str] = None,
        passphrase: Optional[str] = None,
        default_timeout: int = 30,
        output_max_chars: int = 3000,
    ):
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

    def _is_conn_alive(self) -> bool:
        """检查 asyncssh 连接是否存活。
        注意：asyncssh 的 SSHClientConnection 没有 is_closing() 方法，
        需通过内部 _closing 属性或捕获 AttributeError 来判断。
        """
        if self._conn is None:
            return False
        try:
            return not self._conn._closing
        except AttributeError:
            return False

    async def _get_conn(self):
        """获取（或重建）SSH 连接。"""
        from astrbot.api import logger

        # 1. 快速路径：检查现有连接
        async with self._lock:
            if self._is_conn_alive():
                return self._conn

        # 2. 慢速路径：在锁外建立连接（避免阻塞事件循环）
        logger.info(f"SSHManager: 正在连接 {self.username}@{self.host}:{self.port} ...")

        # 构建认证参数
        use_key = bool(self.key_path and self.key_path.strip())
        connect_kwargs = dict(
            port=self.port,
            username=self.username,
            known_hosts=None,          # 不校验主机指纹（兼容公网场景）
            login_timeout=60,          # 公网场景延长握手等待
            **_COMPAT_ALGS,            # ← 宽容算法集合（核心修复）
        )

        if use_key:
            connect_kwargs["client_keys"] = [self.key_path]
            if self.passphrase:
                connect_kwargs["passphrase"] = self.passphrase
            # 不传 password，仅走密钥认证
        else:
            # 仅密码认证：明确禁用密钥，避免 asyncssh 自动尝试本地 ~/.ssh/
            connect_kwargs["password"] = self.password
            connect_kwargs["client_keys"] = []
            connect_kwargs["preferred_auth"] = "password"

        try:
            new_conn = await asyncssh.connect(self.host, **connect_kwargs)

            # 3. 存储结果（双重检查，防并发重复创建）
            async with self._lock:
                if self._is_conn_alive():
                    new_conn.close()
                    return self._conn
                self._conn = new_conn
                logger.info(f"SSHManager: 成功连接至 {self.host}")
                return self._conn

        except asyncssh.DisconnectError as e:
            logger.error(
                f"SSHManager: 服务器主动断开 (code={e.code}): {e.reason}"
            )
            raise
        except asyncssh.PermissionDenied as e:
            logger.error(f"SSHManager: 认证失败，请检查用户名/密码/密钥: {e}")
            raise
        except asyncssh.ConnectionLost as e:
            logger.error(
                f"SSHManager: 连接丢失 (多为握手算法不兼容): {e}"
            )
            raise
        except Exception as e:
            logger.error(
                f"SSHManager: 连接异常 ({type(e).__name__}): {e}"
            )
            raise

    def _truncate_output(self, text: str) -> str:
        if not text:
            return ""
        if len(text) > self.output_max_chars:
            return text[: self.output_max_chars] + "\n...(由于长度限制已截断)"
        return text

    def _reset_conn(self):
        """标记连接已失效，下次调用 _get_conn 时将重建。"""
        self._conn = None

    async def execute_command(
        self, command: str, timeout: Optional[int] = None
    ) -> Tuple[int, str, str]:
        """执行命令，返回 (exit_status, stdout, stderr)。"""
        exec_timeout = timeout if timeout is not None else self.default_timeout
        try:
            conn = await self._get_conn()
            result = await asyncio.wait_for(conn.run(command), timeout=exec_timeout)
            return (
                result.exit_status,
                self._truncate_output(result.stdout),
                self._truncate_output(result.stderr),
            )
        except (asyncssh.ConnectionLost, asyncssh.DisconnectError):
            self._reset_conn()
            return -1, "", "SSH 连接丢失，请重新执行命令"
        except asyncio.TimeoutError:
            return -1, "", f"命令执行超时（{exec_timeout}s）"
        except Exception as e:
            return -1, "", str(e)

    async def execute_install(
        self, command: str, timeout: int = 600
    ) -> Tuple[int, str, str]:
        """包安装专供逻辑（自动补 -y 与 DEBIAN_FRONTEND）。"""
        wrapped = f"DEBIAN_FRONTEND=noninteractive {command}"
        for pkg_mgr in ["apt-get install", "apt install", "yum install", "dnf install"]:
            if pkg_mgr in wrapped and "-y" not in wrapped:
                wrapped = wrapped.replace(pkg_mgr, f"{pkg_mgr} -y")

        try:
            conn = await self._get_conn()
            result = await asyncio.wait_for(
                conn.run(wrapped, term_type="xterm"), timeout=timeout
            )
            return (
                result.exit_status,
                self._truncate_output(result.stdout),
                self._truncate_output(result.stderr),
            )
        except (asyncssh.ConnectionLost, asyncssh.DisconnectError):
            self._reset_conn()
            return -1, "", "SSH 连接丢失"
        except asyncio.TimeoutError:
            return -1, "", f"安装命令超时（{timeout}s）"
        except Exception as e:
            return -1, "", str(e)

    async def read_file(self, filepath: str) -> str:
        """读取远端文件内容。"""
        try:
            conn = await self._get_conn()
            result = await asyncio.wait_for(
                conn.run(f'cat "{filepath}"'), timeout=self.default_timeout
            )
            if result.exit_status != 0:
                return f"Error: {result.stderr or 'File not found'}"
            return self._truncate_output(result.stdout)
        except (asyncssh.ConnectionLost, asyncssh.DisconnectError):
            self._reset_conn()
            return "SSH Read Error: 连接丢失"
        except Exception as e:
            return f"SSH Read Error: {e}"

    async def write_file(self, filepath: str, content: str) -> str:
        """安全写入远端文件。"""
        try:
            conn = await self._get_conn()
            cmd = (
                f"mkdir -p \"$(dirname '{filepath}')\" && "
                f"cat > '{filepath}' << 'HEREDOC_EOF'\n{content}\nHEREDOC_EOF"
            )
            result = await asyncio.wait_for(
                conn.run(cmd), timeout=self.default_timeout
            )
            if result.exit_status != 0:
                return f"Error: {result.stderr}"
            return f"Successfully written to '{filepath}'"
        except (asyncssh.ConnectionLost, asyncssh.DisconnectError):
            self._reset_conn()
            return "SSH Write Error: 连接丢失"
        except Exception as e:
            return f"SSH Write Error: {e}"
