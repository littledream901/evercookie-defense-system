"""集成测试全局 fixture。

策略：
- 通过 docker-compose 启动 mysql-test / redis-test / clickhouse-test 三容器。
- 通过环境变量 SKIP_INTEGRATION=1 可跳过（本地无 docker 时）。
- 每个测试模块可选择 admin 或 gateway 作为顶层包，通过子目录 conftest 决定 sys.path。
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Iterator

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE = Path(__file__).parent / "docker-compose.test.yml"

MYSQL_PORT = 33306
REDIS_PORT = 36379
CLICKHOUSE_PORT = 38123

ADMIN_DB_URL = (
    f"mysql+aiomysql://fangyu:fangyu@127.0.0.1:{MYSQL_PORT}/fangyu_test"
)
ADMIN_DB_SYNC_URL = (
    f"mysql+pymysql://fangyu:fangyu@127.0.0.1:{MYSQL_PORT}/fangyu_test"
)
REDIS_URL = f"redis://127.0.0.1:{REDIS_PORT}/0"
CLICKHOUSE_URL = f"http://127.0.0.1:{CLICKHOUSE_PORT}"


def _wait_port(host: str, port: int, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with closing(socket.socket()) as sock:
            sock.settimeout(1.0)
            try:
                sock.connect((host, port))
                return True
            except OSError:
                time.sleep(1.0)
    return False


def _docker_available() -> bool:
    return shutil.which("docker") is not None


@pytest.fixture(scope="session")
def integration_stack() -> Iterator[dict]:
    """启动/销毁集成测试用的三容器栈。"""
    if os.getenv("SKIP_INTEGRATION"):
        pytest.skip("集成测试被 SKIP_INTEGRATION 环境变量跳过")
    if not _docker_available():
        pytest.skip("未检测到 docker 可执行文件，跳过集成测试")

    up = subprocess.run(
        ["docker", "compose", "-f", str(_COMPOSE), "up", "-d"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
    )
    if up.returncode != 0:
        pytest.skip(f"docker compose up 失败: {up.stderr.strip()}")

    ok = all(
        _wait_port("127.0.0.1", port, timeout=90)
        for port in (MYSQL_PORT, REDIS_PORT, CLICKHOUSE_PORT)
    )
    if not ok:
        subprocess.run(
            ["docker", "compose", "-f", str(_COMPOSE), "down", "-v"],
            cwd=str(_ROOT),
            capture_output=False,
        )
        pytest.skip("集成测试依赖端口未就绪")

    time.sleep(3)  # MySQL 授权初始化余量

    yield {
        "admin_db_url": ADMIN_DB_URL,
        "admin_db_sync_url": ADMIN_DB_SYNC_URL,
        "redis_url": REDIS_URL,
        "clickhouse_url": CLICKHOUSE_URL,
    }

    if not os.getenv("KEEP_INTEGRATION_STACK"):
        subprocess.run(
            ["docker", "compose", "-f", str(_COMPOSE), "down", "-v"],
            cwd=str(_ROOT),
            capture_output=True,
        )


@pytest.fixture(scope="session")
def integration_env(integration_stack: dict) -> Iterator[dict]:
    """把连接信息注入进程环境变量。"""
    old = {}
    mapping = {
        "ADMIN_DATABASE_URL": integration_stack["admin_db_url"],
        "ADMIN_REDIS_URL": integration_stack["redis_url"],
        "ADMIN_CLICKHOUSE_URL": integration_stack["clickhouse_url"],
        # 长度需满足 AdminSettings.jwt_secret 的 min_length=32
        "ADMIN_JWT_SECRET": "integration-test-secret-0123456789abcdef",
        "GATEWAY_REDIS_URL": integration_stack["redis_url"],
        "WORKER_REDIS_URL": integration_stack["redis_url"],
        "WORKER_CLICKHOUSE_URL": integration_stack["clickhouse_url"],
    }
    for k, v in mapping.items():
        old[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        yield mapping
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
