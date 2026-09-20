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

    # Verify Install dependencies step includes editable install
    install_step = next(s for s in steps if "Install dependencies" in s.get("name", ""))
    install_cmd = install_step.get("run", "")
    assert "pip install -e ." in install_cmd

    # Verify Run MECUT Radar step environment
    run_step = next(s for s in steps if "Run MECUT Radar" in s.get("name", ""))
    env = run_step.get("env", {})
    assert env.get("DRY_RUN") == "false"
    assert env.get("APP_ENV") == "production"
    assert env.get("NOTIFICATION_LIMIT") == "50"
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
    assert 'rm -f "$TMP_INDEX"' in persist_cmd
    assert "trap" in persist_cmd


def test_ci_workflow_file_exists() -> None:
    """Test that ci.yml exists and has valid YAML syntax."""
    ci_path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
    assert ci_path.is_file(), f"CI workflow file not found at {ci_path}"

    with open(ci_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert isinstance(data, dict)
    assert data.get("name") == "CI"


def test_ci_workflow_triggers() -> None:
    """Test that ci.yml triggers on push and pull_request to main."""
    ci_path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
    with open(ci_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    triggers = data.get("on")
    assert isinstance(triggers, dict)

    # Push trigger includes main
    assert "push" in triggers
    push_branches = triggers["push"].get("branches", [])
    assert "main" in push_branches

    # Pull request trigger targets main
    assert "pull_request" in triggers
    pr_branches = triggers["pull_request"].get("branches", [])
    assert "main" in pr_branches


def test_ci_workflow_permissions_and_secrets() -> None:
    """Test least-privilege permissions and ensure no production secrets or db-state are used."""
    ci_path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
    with open(ci_path, "r", encoding="utf-8") as f:
        raw_text = f.read()
        data = yaml.safe_load(raw_text)

    # Permissions must not grant contents: write
    permissions = data.get("permissions")
    assert isinstance(permissions, dict)
    assert permissions.get("contents") == "read"
    assert "write" not in raw_text.lower().split("permissions:")[1].split("jobs:")[0]

    # No production secrets or state branch referenced
    assert "TELEGRAM_BOT_TOKEN" not in raw_text
    assert "TELEGRAM_CHAT_ID" not in raw_text
    assert "db-state" not in raw_text
    assert "mecut_radar.db" not in raw_text


def test_ci_workflow_steps() -> None:
    """Test that Python 3.11, dependency installs, and test coverage execution are configured."""
    ci_path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
    with open(ci_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    job = data.get("jobs", {}).get("test", {})
    assert job.get("runs-on") == "ubuntu-latest"

    steps = job.get("steps", [])

    # Checkout step exists
    assert any("actions/checkout" in s.get("uses", "") for s in steps)

    # Python 3.11 configured
    python_step = next(s for s in steps if "actions/setup-python" in s.get("uses", ""))
    assert python_step.get("with", {}).get("python-version") == "3.11"

    # Dependency installation includes requirements.txt and pip install -e .
    install_step = next(s for s in steps if "pip install" in s.get("run", ""))
    install_cmd = install_step.get("run", "")
    assert "requirements.txt" in install_cmd
    assert "pip install -e ." in install_cmd

    # Pytest with coverage executed
    test_step = next(s for s in steps if "pytest -v" in s.get("run", ""))
    test_cmd = test_step.get("run", "")
    assert "pytest -v --cov=mecut_radar --cov-report=term-missing" in test_cmd

