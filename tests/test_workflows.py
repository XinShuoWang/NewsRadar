from pathlib import Path
import os
import subprocess
import sys

import yaml


def _workflow_run_commands(path: str) -> list[str]:
    commands: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- run: "):
            commands.append(stripped.removeprefix("- run: "))
    return commands


def _workflow_steps(path: str) -> list[dict]:
    workflow = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    job = next(iter(workflow["jobs"].values()))
    return job["steps"]


def test_daily_workflow_contains_required_secrets():
    commands = _workflow_run_commands(".github/workflows/daily-digest.yml")
    assert "PYTHONPATH=src python -m newsradar.main" in commands
    workflow = Path(".github/workflows/daily-digest.yml").read_text(encoding="utf-8")
    assert "LLM_API_KEY" in workflow
    assert "SMTP_USERNAME" in workflow
    assert "SMTP_PASSWORD" in workflow


def test_daily_workflow_runs_at_8am_shanghai_time():
    workflow = yaml.safe_load(Path(".github/workflows/daily-digest.yml").read_text(encoding="utf-8"))
    trigger = workflow.get("on", workflow.get(True))
    schedules = trigger["schedule"]

    assert schedules == [{"cron": "0 0 * * *"}]


def test_daily_workflow_persists_incremental_state_back_to_repo():
    workflow = yaml.safe_load(Path(".github/workflows/daily-digest.yml").read_text(encoding="utf-8"))
    job = next(iter(workflow["jobs"].values()))

    assert job["permissions"]["contents"] == "write"

    run_snippets = [step.get("run", "") for step in job["steps"] if "run" in step]
    assert any("git add state" in snippet for snippet in run_snippets)
    assert not any("git add archive" in snippet for snippet in run_snippets)
    assert any("git commit -m \"chore: update NewsRadar dedup state [skip ci]\"" in snippet for snippet in run_snippets)
    assert any("git push" in snippet for snippet in run_snippets)


def test_daily_workflow_does_not_upload_archive_artifacts():
    steps = _workflow_steps(".github/workflows/daily-digest.yml")

    upload_steps = [step for step in steps if step.get("uses") == "actions/upload-artifact@v4"]

    assert upload_steps == []


def test_main_module_entrypoint_runs_without_github_actions(tmp_path):
    env = os.environ.copy()
    env.pop("GITHUB_ACTIONS", None)
    env["PYTHONPATH"] = "src"
    (tmp_path / "official.yaml").write_text("sources: []\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "newsradar.main",
            "--official-sources-path",
            str(tmp_path / "official.yaml"),
            "--state-root",
            str(tmp_path / "state"),
        ],
        cwd=Path("."),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert (tmp_path / "state" / "seen_items.json").exists()
    assert not (tmp_path / "state" / "source_cursors.json").exists()
    assert not (tmp_path / "archive").exists()


def test_gitignore_keeps_state_files_tracked_without_archive_rule():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "archive/*" not in gitignore
    assert "state/" not in gitignore
