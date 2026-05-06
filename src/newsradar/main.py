"""NewsRadar CLI 入口。"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from newsradar.app import run_daily_digest
from newsradar.config import load_settings
from newsradar.logging import configure_logging
from newsradar.paths import repo_root


def main(argv: list[str] | None = None) -> int:
    """解析命令行参数并启动每日流程。"""

    args = _build_parser().parse_args(argv)
    configure_logging(args.log_level)
    state_root = args.state_root or repo_root() / "state"
    settings = load_settings(
        official_sources_path=args.official_sources_path,
        state_root=state_root,
    )
    return run_daily_digest(
        run_date=date.fromisoformat(args.run_date),
        settings=settings,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成 NewsRadar 每日日报。")
    parser.add_argument("--run-date", default=date.today().isoformat(), help="日报日期，默认今天。")
    parser.add_argument(
        "--official-sources-path",
        default=repo_root() / "config" / "source.yaml",
        type=Path,
        help="官方来源注册表路径。",
    )
    parser.add_argument(
        "--state-root",
        default=None,
        type=Path,
        help="去重状态目录，默认使用仓库根目录下的 state/。",
    )
    parser.add_argument(
        "--log-level",
        default="TRACE",
        choices=("TRACE", "DEBUG", "INFO", "WARNING", "ERROR"),
        help="日志等级，默认 TRACE。",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
