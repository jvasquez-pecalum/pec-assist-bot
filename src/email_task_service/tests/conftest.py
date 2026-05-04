"""
Shared pytest fixtures and .env loader for all test modules.
"""

from pathlib import Path
import os


def pytest_configure(config):
    """Load .env before tests run so env-driven services pick up real credentials."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())
