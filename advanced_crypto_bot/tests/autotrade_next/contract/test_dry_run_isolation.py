"""Negative dependency and credential isolation contracts for DRY RUN."""

import ast
from pathlib import Path

from autotrade_next.ports.venue import VenuePort


ROOT = Path(__file__).parents[3] / "autotrade_next"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _reachable_local_files(entry: Path) -> set[Path]:
    pending, reached = [entry], set()
    while pending:
        path = pending.pop()
        if path in reached:
            continue
        reached.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            target = None
            if node.level:
                base = path.parent
                for _ in range(node.level - 1):
                    base = base.parent
                target = base.joinpath(*node.module.split(".")).with_suffix(".py")
            elif node.module.startswith("autotrade_next."):
                suffix = node.module.removeprefix("autotrade_next.")
                target = ROOT.joinpath(*suffix.split(".")).with_suffix(".py")
            if target is not None and target.is_file() and target not in reached:
                pending.append(target)
    return reached


def test_simulator_dependency_graph_has_no_io_or_live_submission_path():
    entries = (ROOT / "domain" / "simulator.py", ROOT / "ports" / "venue.py")
    reachable = set().union(*(_reachable_local_files(path) for path in entries))
    forbidden_modules = {
        "requests", "httpx", "aiohttp", "socket", "sqlite3", "redis",
        "subprocess", "os", "pathlib", "importlib",
    }
    forbidden_calls = {"hash", "open", "exec", "eval", "compile", "__import__"}
    for path in reachable:
        assert path.is_relative_to(ROOT / "domain") or path == ROOT / "ports" / "venue.py"
        imports = _imports(path)
        assert not {name.split(".")[0] for name in imports}.intersection(forbidden_modules)
        assert all("live_submit" not in name and "credential" not in name for name in imports)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr != "import_module"


def test_venue_protocol_is_schema_only_and_has_no_credential_provider():
    source = (ROOT / "ports" / "venue.py").read_text(encoding="utf-8").lower()
    assert "api_key" not in source
    assert "api_secret" not in source
    assert "credential" not in source
    assert VenuePort.__module__ == "autotrade_next.ports.venue"
