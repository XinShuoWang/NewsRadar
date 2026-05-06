"""仓库路径工具。"""

from pathlib import Path


def repo_root() -> Path:
    """返回项目仓库根目录。"""

    return Path(__file__).resolve().parents[2]
