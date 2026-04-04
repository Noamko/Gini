"""Sandbox manager — creates and manages ephemeral Docker containers for safe tool execution."""
import asyncio

import structlog

logger = structlog.get_logger("sandbox")

SANDBOX_IMAGE = "gini-sandbox:latest"
CONTAINER_PREFIX = "gini-sandbox-"
DEFAULT_TIMEOUT = 30
DEFAULT_MEM_LIMIT = "512m"
DEFAULT_CPU_PERIOD = 100000
DEFAULT_CPU_QUOTA = 50000  # 50% of one CPU

# Docker network for sandboxes with internet access
# Created by docker-compose as gini_sandbox
SANDBOX_NETWORK = "gini_sandbox"


class SandboxResult:
    def __init__(self, exit_code: int, stdout: str, stderr: str):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def output(self) -> str:
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(f"STDERR:\n{self.stderr}")
        return "\n".join(parts) if parts else "(no output)"


class SandboxManager:
    """Manages ephemeral Docker containers for sandboxed command execution.

    Uses the Docker CLI via subprocess to avoid extra dependencies.
    """

    async def execute(
        self,
        command: str,
        timeout: int = DEFAULT_TIMEOUT,
        mem_limit: str = DEFAULT_MEM_LIMIT,
        allow_network: bool = False,
    ) -> SandboxResult:
        """Run a command in an ephemeral sandbox container.

        Args:
            command: Shell command to execute.
            timeout: Max execution time in seconds.
            mem_limit: Docker memory limit.
            allow_network: If True, use the sandbox network (internet access).
                          If False, use --network none (fully isolated).
        """
        import uuid

        container_name = f"{CONTAINER_PREFIX}{uuid.uuid4().hex[:12]}"

        if allow_network:
            network_args = ["--network", SANDBOX_NETWORK]
        else:
            network_args = ["--network", "none"]

        docker_cmd = [
            "docker", "run",
            "--rm",
            "--name", container_name,
            *network_args,
            "--memory", mem_limit,
            "--cpu-period", str(DEFAULT_CPU_PERIOD),
            "--cpu-quota", str(DEFAULT_CPU_QUOTA),
            "--tmpfs", "/tmp:rw,size=128m",
            "--tmpfs", "/workspace:rw,size=64m",
            "--security-opt", "no-new-privileges",
            SANDBOX_IMAGE,
            "bash", "-c", command,
        ]

        await logger.ainfo("sandbox_exec_start", container=container_name, command=command[:200], network=allow_network)

        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout + 5  # extra grace period
            )

            stdout = stdout_bytes.decode("utf-8", errors="replace")[:50000]
            stderr = stderr_bytes.decode("utf-8", errors="replace")[:10000]

            result = SandboxResult(
                exit_code=proc.returncode or 0,
                stdout=stdout,
                stderr=stderr,
            )

            await logger.ainfo(
                "sandbox_exec_done",
                container=container_name,
                exit_code=result.exit_code,
                stdout_len=len(stdout),
            )
            return result

        except TimeoutError:
            kill_proc = await asyncio.create_subprocess_exec(
                "docker", "kill", container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await kill_proc.wait()
            await logger.awarn("sandbox_timeout", container=container_name, timeout=timeout)
            return SandboxResult(exit_code=137, stdout="", stderr=f"Command timed out after {timeout}s")

        except Exception as e:
            await logger.aerror("sandbox_exec_error", container=container_name, error=str(e))
            return SandboxResult(exit_code=1, stdout="", stderr=str(e))

    async def ensure_image(self) -> bool:
        """Check if the sandbox image exists, return True if it does."""
        proc = await asyncio.create_subprocess_exec(
            "docker", "image", "inspect", SANDBOX_IMAGE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0


# Singleton
sandbox_manager = SandboxManager()
