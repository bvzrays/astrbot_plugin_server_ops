import asyncssh
import asyncio
from typing import Tuple, Optional

# -----------------------------------------------------------------------------------
# 宽容算法集合：覆盖新旧服务器常用的 kex / 加密 / MAC / 主机密钥算法。
# -----------------------------------------------------------------------------------
_COMPAT_ALGS = dict(
    kex_algs=[
        "curve25519-sha256",
        "curve25519-sha256@libssh.org",
        "ecdh-sha2-nistp521",
        "ecdh-sha2-nistp384",
        "ecdh-sha2-nistp256",
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
    """异步 SSH 管理器 (v3.0.0 Refactored)"""

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
        if self._conn is None:
            return False
        try:
            return not self._conn._closing
        except AttributeError:
            return False

    async def _get_conn(self):
        from astrbot.api import logger

        async with self._lock:
            if self._is_conn_alive():
                return self._conn

        connect_kwargs = dict(
            port=self.port,
            username=self.username,
            known_hosts=None,
            login_timeout=60,
            **_COMPAT_ALGS,
        )

        if self.key_path and self.key_path.strip():
            connect_kwargs["client_keys"] = [self.key_path]
            if self.passphrase:
                connect_kwargs["passphrase"] = self.passphrase
        else:
            connect_kwargs["password"] = self.password
            connect_kwargs["client_keys"] = []
            connect_kwargs["preferred_auth"] = "password"

        try:
            new_conn = await asyncssh.connect(self.host, **connect_kwargs)
            async with self._lock:
                if self._is_conn_alive():
                    new_conn.close()
                    return self._conn
                self._conn = new_conn
                return self._conn
        except Exception as e:
            logger.error(f"SSHManager: Connection error ({type(e).__name__}): {e}")
            raise

    def _truncate_output(self, text: str) -> str:
        if not text: return ""
        if len(text) > self.output_max_chars:
            return text[: self.output_max_chars] + "\n...(truncated due to length)"
        return text

    def _reset_conn(self):
        self._conn = None

    async def execute_command(
        self, command: str, timeout: Optional[int] = None
    ) -> Tuple[int, str, str]:
        exec_timeout = timeout if timeout is not None else self.default_timeout
        try:
            conn = await self._get_conn()
            result = await asyncio.wait_for(conn.run(command), timeout=exec_timeout)
            return (result.exit_status, self._truncate_output(result.stdout), self._truncate_output(result.stderr))
        except (asyncssh.ConnectionLost, asyncssh.DisconnectError):
            self._reset_conn()
            return -1, "", "SSH connection lost"
        except Exception as e:
            return -1, "", str(e)

    async def execute_install(self, command: str, timeout: int = 600) -> Tuple[int, str, str]:
        wrapped = f"DEBIAN_FRONTEND=noninteractive {command}"
        for pkg_mgr in ["apt-get install", "apt install", "yum install", "dnf install"]:
            if pkg_mgr in wrapped and "-y" not in wrapped:
                wrapped = wrapped.replace(pkg_mgr, f"{pkg_mgr} -y")
        try:
            conn = await self._get_conn()
            result = await asyncio.wait_for(conn.run(wrapped, term_type="xterm"), timeout=timeout)
            return (result.exit_status, self._truncate_output(result.stdout), self._truncate_output(result.stderr))
        except Exception as e:
            return -1, "", str(e)

    async def read_file(self, filepath: str) -> str:
        try:
            conn = await self._get_conn()
            result = await asyncio.wait_for(conn.run(f'cat "{filepath}"'), timeout=self.default_timeout)
            if result.exit_status != 0:
                return f"Error: {result.stderr or 'File not found'}"
            return self._truncate_output(result.stdout)
        except Exception as e:
            return f"SSH Read Error: {e}"

    async def write_file(self, filepath: str, content: str) -> str:
        try:
            conn = await self._get_conn()
            cmd = (
                f"mkdir -p \"$(dirname '{filepath}')\" && "
                f"cat > '{filepath}' << 'HEREDOC_EOF'\n{content}\nHEREDOC_EOF"
            )
            result = await asyncio.wait_for(conn.run(cmd), timeout=self.default_timeout)
            return f"Successfully written to '{filepath}'" if result.exit_status == 0 else f"Error: {result.stderr}"
        except Exception as e:
            return f"SSH Write Error: {e}"

    async def upload_binary(self, data: bytes, remote_path: str) -> str:
        try:
            conn = await self._get_conn()
            parent_dir = "/".join(remote_path.replace("\\", "/").split("/")[:-1])
            if parent_dir: await conn.run(f"mkdir -p '{parent_dir}'")
            async with conn.start_sftp_client() as sftp:
                async with sftp.open(remote_path, 'wb') as f:
                    await f.write(data)
            return f"Successfully uploaded binary to '{remote_path}'"
        except Exception as e:
            return f"SSH Upload Error: {e}"
