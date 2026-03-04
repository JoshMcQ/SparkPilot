from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(
    os.getenv("SPARKPILOT_RUN_AIRFLOW_COMPOSE") != "1",
    reason="Set SPARKPILOT_RUN_AIRFLOW_COMPOSE=1 to run docker-compose integration.",
)
def test_airflow_provider_docker_compose_integration() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is not installed in this environment.")

    compose_file = Path(__file__).resolve().parents[1] / "providers" / "airflow" / "docker-compose.integration.yml"
    up_cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "up",
        "--build",
        "--abort-on-container-exit",
        "--exit-code-from",
        "airflow-integration",
    ]
    down_cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "down",
        "-v",
        "--remove-orphans",
    ]
    try:
        subprocess.run(up_cmd, check=True)
    finally:
        subprocess.run(down_cmd, check=False)

