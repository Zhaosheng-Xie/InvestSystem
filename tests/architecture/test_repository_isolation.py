from __future__ import annotations

import ast
import os
import tomllib
from pathlib import Path

BANNED_PROVIDER_MODULE = "investment_research_kb"
BANNED_SIBLING_IDENTIFIERS = (
    "investmentresearchkb",
    "investment_research_kb",
    "investment-research-kb",
)


def python_files(repository_root: Path) -> list[Path]:
    return sorted((repository_root / "src").rglob("*.py"))


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def docstring_node_ids(tree: ast.AST) -> set[int]:
    identifiers: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                identifiers.add(id(first.value))
    return identifiers


def test_source_never_imports_the_kb_package_or_mutates_pythonpath(
    repository_root: Path,
) -> None:
    violations: list[str] = []
    for path in python_files(repository_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == BANNED_PROVIDER_MODULE or alias.name.startswith(
                        f"{BANNED_PROVIDER_MODULE}."
                    ):
                        violations.append(f"{path}:{node.lineno}: banned import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == BANNED_PROVIDER_MODULE or module.startswith(
                    f"{BANNED_PROVIDER_MODULE}."
                ):
                    violations.append(f"{path}:{node.lineno}: banned import {module}")
            elif isinstance(node, ast.Call):
                call_name = dotted_name(node.func)
                if call_name in {
                    "sys.path.append",
                    "sys.path.extend",
                    "sys.path.insert",
                }:
                    violations.append(f"{path}:{node.lineno}: sys.path mutation")
                if call_name in {"__import__", "importlib.import_module"} and node.args:
                    argument = node.args[0]
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        if argument.value == BANNED_PROVIDER_MODULE or argument.value.startswith(
                            f"{BANNED_PROVIDER_MODULE}."
                        ):
                            violations.append(f"{path}:{node.lineno}: dynamic banned import")
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets: list[ast.AST]
                if isinstance(node, ast.Assign):
                    targets = list(node.targets)
                else:
                    targets = [node.target]
                if any(dotted_name(target) == "sys.path" for target in targets):
                    violations.append(f"{path}:{node.lineno}: sys.path assignment")

    assert violations == []


def test_strategy_code_cannot_import_provider_integrations(repository_root: Path) -> None:
    strategies_root = repository_root / "src" / "invest_system" / "strategies"
    if not strategies_root.exists():
        return

    violations: list[str] = []
    for path in strategies_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                if module == "invest_system.integrations" or module.startswith(
                    "invest_system.integrations."
                ):
                    violations.append(f"{path}:{node.lineno}: {module}")

    assert violations == []


def test_source_contains_no_executable_sibling_repository_reference(
    repository_root: Path,
) -> None:
    """Ignore prose docstrings while rejecting executable sibling-repo literals."""

    violations: list[str] = []
    for path in python_files(repository_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        documentation = docstring_node_ids(tree)
        for node in ast.walk(tree):
            if id(node) in documentation:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                normalized = node.value.casefold().replace("\\", "/")
                if any(identifier in normalized for identifier in BANNED_SIBLING_IDENTIFIERS):
                    violations.append(f"{path}:{node.lineno}: sibling repository literal")

    assert violations == []


def test_source_has_no_static_kb_internal_path_reads(repository_root: Path) -> None:
    """Reject executable filesystem calls aimed at provider-internal path components."""

    filesystem_calls = {
        "open",
        "pathlib.path",
        "path",
        "read_text",
        "read_bytes",
        "sqlite3.connect",
    }
    forbidden_components = {"raw", "staging", "published"}
    forbidden_discovery_calls = {"os.chdir", "os.getcwd", "path.cwd", "path.home"}
    violations: list[str] = []

    for path in python_files(repository_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (dotted_name(node.func) or "").casefold()
            if name in forbidden_discovery_calls:
                violations.append(f"{path}:{node.lineno}: external path discovery via {name}")
            if name not in filesystem_calls and not name.endswith((".read_text", ".read_bytes")):
                continue
            for argument in (*node.args, *(keyword.value for keyword in node.keywords)):
                for nested in ast.walk(argument):
                    if not isinstance(nested, ast.Constant) or not isinstance(nested.value, str):
                        continue
                    normalized = nested.value.casefold().replace("\\", "/")
                    components = {part for part in normalized.split("/") if part}
                    if (
                        any(identifier in normalized for identifier in BANNED_SIBLING_IDENTIFIERS)
                        or ".." in components
                        or components.intersection(forbidden_components)
                    ):
                        violations.append(f"{path}:{node.lineno}: forbidden path literal")

    assert violations == []


def test_dependencies_contain_no_kb_editable_vcs_or_local_path(
    repository_root: Path,
) -> None:
    project = tomllib.loads((repository_root / "pyproject.toml").read_text(encoding="utf-8"))
    dependency_groups = [project["project"].get("dependencies", [])]
    dependency_groups.extend(project["project"].get("optional-dependencies", {}).values())
    declared = [dependency for group in dependency_groups for dependency in group]

    forbidden_fragments = (
        "investment-research-kb",
        "investment_research_kb",
        "git+",
        "file:",
        "../",
        "..\\",
        " @ ",
    )
    for dependency in declared:
        normalized = dependency.casefold()
        assert not any(fragment in normalized for fragment in forbidden_fragments)

    assert any(
        dependency.casefold().startswith("rfc3339-validator")
        for dependency in project["project"]["dependencies"]
    )

    for name in ("requirements.lock", "requirements-dev.lock"):
        lock_path = repository_root / name
        assert lock_path.is_file(), f"missing required lock: {name}"
        normalized = lock_path.read_text(encoding="utf-8").casefold()
        assert "investment-research-kb" not in normalized
        assert "investment_research_kb" not in normalized
        assert "git+" not in normalized
        assert "file://" not in normalized


def test_default_runtime_paths_are_project_owned_and_fail_closed(
    repository_root: Path,
) -> None:
    config = tomllib.loads(
        (repository_root / "config" / "default.toml").read_text(encoding="utf-8")
    )
    resolved_root = repository_root.resolve()

    for name, configured_path in config["paths"].items():
        candidate = Path(configured_path)
        assert not candidate.is_absolute(), f"{name} must be project-relative"
        assert candidate.parts[0] == "var", f"{name} must be under InvestSystem var/"
        resolved = (repository_root / candidate).resolve()
        assert resolved.is_relative_to(resolved_root), f"{name} escapes the repository"

    assert config["safety"] == {
        "fail_closed": True,
        "allow_external_network": False,
        "allow_broker_connections": False,
        "allow_order_submission": False,
    }
    assert config["strategy_inputs"] == {"max_refs_per_run": 1}
    assert config["release_delivery"] == {
        "allowed_transports": ["read_only_http_api", "immutable_export"]
    }
    assert config["release_cache"] == {
        "soft_limit_gib": 20,
        "auto_delete_historically_referenced": False,
        "automatic_gc_enabled": False,
    }
    assert config["release_withdrawal"] == {
        "block_new_runs": True,
        "retain_historical_material": True,
        "historical_replay_mode": "audit_replay",
    }


def test_repository_has_no_submodule_symlink_junction_or_hardlink(
    repository_root: Path,
) -> None:
    assert not (repository_root / ".gitmodules").exists()
    scan_roots = ("src", "contracts", "tests", "config", "scripts")
    violations: list[str] = []

    for root_name in scan_roots:
        root = repository_root / root_name
        if not root.exists():
            continue
        for path in (root, *root.rglob("*")):
            if path.is_symlink():
                violations.append(f"symbolic link: {path}")
                continue
            is_junction = getattr(path, "is_junction", lambda: False)
            if is_junction():
                violations.append(f"junction: {path}")
                continue
            if path.is_file() and os.stat(path).st_nlink > 1:
                violations.append(f"hard link: {path}")

    assert violations == []


def test_required_ci_checks_out_only_this_repository_without_services(
    repository_root: Path,
) -> None:
    workflow = repository_root / ".github" / "workflows" / "ci.yml"
    assert workflow.is_file()
    text = workflow.read_text(encoding="utf-8").casefold()

    assert "persist-credentials: false" in text
    assert "submodules: false" in text
    assert "submodules: true" not in text
    assert "repository:" not in text
    assert "services:" not in text
    assert "pythonpath" not in text
    assert "investmentresearchkb" not in text
    assert "investment_research_kb" not in text
    assert "python -m mypy" in text
    assert "fetch-depth: 0" in text
    assert 'git diff --check "${{ github.event.pull_request.base.sha }}...head"' in text
    assert 'git diff --check "$before_sha..head"' in text
