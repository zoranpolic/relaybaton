from __future__ import annotations

from pathlib import Path

import pytest

from relaybaton import config, sync
from relaybaton.config import ConfigError
from relaybaton.sync import State


def states(project: Path) -> dict[str, State]:
    return {s.agent: s.state for s in sync.plan(config.load(project))}


def test_everything_missing_at_first(project: Path) -> None:
    assert set(states(project).values()) == {State.MISSING}


def test_write_creates_all_targets_including_nested(project: Path) -> None:
    sync.write(config.load(project))
    assert set(states(project).values()) == {State.OK}
    copilot = (project / ".github" / "copilot-instructions.md").read_text()
    assert "Run `make test` before you push." in copilot
    assert copilot.startswith("<!-- relaybaton:generated source=AGENTS.md agent=copilot")


def test_source_edit_makes_targets_drift(project: Path) -> None:
    cfg = config.load(project)
    sync.write(cfg)
    (project / "AGENTS.md").write_text("# Rules\n\nNew rule.\n")
    assert set(states(project).values()) == {State.DRIFTED}


def test_hand_edit_of_generated_file_is_drift(project: Path) -> None:
    sync.write(config.load(project))
    claude = project / "CLAUDE.md"
    claude.write_text(claude.read_text() + "sneaky local edit\n")
    assert states(project)["claude"] is State.DRIFTED


def test_hand_written_file_is_never_overwritten_without_force(project: Path) -> None:
    (project / "CLAUDE.md").write_text("my own notes\n")
    statuses = sync.write(config.load(project))
    assert {s.agent: s.state for s in statuses}["claude"] is State.UNMANAGED
    assert (project / "CLAUDE.md").read_text() == "my own notes\n"

    sync.write(config.load(project), force=True)
    assert states(project)["claude"] is State.OK


def test_overlay_is_appended_for_one_agent_only(project: Path) -> None:
    (project / "AGENTS.claude.md").write_text("Use the Bash tool sparingly.\n")
    sync.write(config.load(project))
    claude = (project / "CLAUDE.md").read_text()
    gemini = (project / "GEMINI.md").read_text()
    assert "Use the Bash tool sparingly." in claude
    assert "AGENTS.claude.md" in claude.splitlines()[1]
    assert "Use the Bash tool sparingly." not in gemini


def test_render_is_deterministic(project: Path) -> None:
    cfg = config.load(project)
    assert sync.render(cfg, "claude") == sync.render(cfg, "claude")


def test_missing_source_is_a_config_error(project: Path) -> None:
    (project / "AGENTS.md").unlink()
    with pytest.raises(ConfigError, match="source file not found"):
        sync.plan(config.load(project))


def test_diff_shows_the_change(project: Path) -> None:
    sync.write(config.load(project))
    (project / "AGENTS.md").write_text("# Rules\n\nChanged.\n")
    claude = next(s for s in sync.plan(config.load(project)) if s.agent == "claude")
    assert "+Changed." in claude.diff()
    missing = sync.TargetStatus("x", "x.md", State.MISSING, "a", None)
    assert missing.diff() == ""
