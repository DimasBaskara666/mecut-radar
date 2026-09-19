"""Tests for GitHub Actions workflow validation."""

from pathlib import Path
import yaml


def test_workflow_file_exists() -> None:
    """Test that radar.yml exists and has valid YAML syntax."""
    workflow_path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "radar.yml"
    assert workflow_path.is_file(), f"Workflow file not found at {workflow_path}"

    with open(workflow_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert isinstance(data, dict)
    assert data.get("name") == "MECUT Radar"


def test_workflow_triggers_and_concurrency() -> None:
    """Test that triggers, schedule, and concurrency locks are properly configured."""
    workflow_path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "radar.yml"
    with open(workflow_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    triggers = data.get("on")
    assert isinstance(triggers, dict)
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers

    schedules = triggers["schedule"]
    assert isinstance(schedules, list)
    assert len(schedules) == 1
    assert schedules[0].get("cron") == "23 */3 * * *"

    concurrency = data.get("concurrency")
    assert isinstance(concurrency, dict)
    assert concurrency.get("group") == "mecut-radar-pipeline"
    assert concurrency.get("cancel-in-progress") is False

    permissions = data.get("permissions")
    assert isinstance(permissions, dict)
    assert permissions.get("contents") == "write"


def test_workflow_steps_structure() -> None:
    """Test that critical steps exist and are correctly sequenced."""
    workflow_path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "radar.yml"
    with open(workflow_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    job = data.get("jobs", {}).get("radar", {})
    assert job.get("runs-on") == "ubuntu-latest"

    steps = job.get("steps", [])
    step_names = [s.get("name", "") for s in steps]

    assert any("Checkout application" in name for name in step_names)
    assert any("Set up Python" in name for name in step_names)
    assert any("Install dependencies" in name for name in step_names)
    assert any("Restore SQLite" in name for name in step_names)
    assert any("Run MECUT Radar" in name for name in step_names)
    assert any("Checkpoint SQLite" in name for name in step_names)
    assert any("Persist database" in name for name in step_names)

    # Verify Run MECUT Radar step environment
    run_step = next(s for s in steps if "Run MECUT Radar" in s.get("name", ""))
    env = run_step.get("env", {})
    assert env.get("DRY_RUN") == "false"
    assert env.get("APP_ENV") == "production"
    assert "TELEGRAM_BOT_TOKEN" in env
    assert "TELEGRAM_CHAT_ID" in env
    assert "GITHUB_TOKEN" in env

    # Verify Checkpoint step commands
    checkpoint_step = next(s for s in steps if "Checkpoint SQLite" in s.get("name", ""))
    run_cmd = checkpoint_step.get("run", "")
    assert "PRAGMA wal_checkpoint(TRUNCATE)" in run_cmd
    assert "PRAGMA integrity_check" in run_cmd

    # Verify Persist step commands
    persist_step = next(s for s in steps if "Persist database" in s.get("name", ""))
    persist_cmd = persist_step.get("run", "")
    assert "db-state" in persist_cmd
    assert "git commit-tree" in persist_cmd
    assert "git push origin" in persist_cmd
