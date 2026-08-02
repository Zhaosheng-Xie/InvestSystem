from __future__ import annotations

import ast
from pathlib import Path

BANNED_LAYERS = ("invest_system.integrations", "invest_system.storage")
BANNED_RELATIVE_ROOTS = {"integrations", "storage"}


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def forbidden_layer_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
            relative_root = (node.module or "").split(".", maxsplit=1)[0]
            imported_roots = {alias.name.split(".", maxsplit=1)[0] for alias in node.names}
            if node.level and (
                relative_root in BANNED_RELATIVE_ROOTS
                or imported_roots.intersection(BANNED_RELATIVE_ROOTS)
            ):
                violations.append(f"{path}:{node.lineno}: relative forbidden layer import")
        elif isinstance(node, ast.Call):
            call_name = _dotted_name(node.func)
            if call_name not in {"__import__", "importlib.import_module"} or not node.args:
                continue
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                modules = [argument.value.lstrip(".")]
        for module in modules:
            if any(module == banned or module.startswith(f"{banned}.") for banned in BANNED_LAYERS):
                violations.append(f"{path}:{getattr(node, 'lineno', 0)}: {module}")
    return violations


def test_domain_and_strategy_packages_do_not_import_provider_or_storage_layers(
    repository_root: Path,
) -> None:
    source_root = repository_root / "src" / "invest_system"
    layer_roots = (source_root / "domain", source_root / "strategies")
    violations = [
        violation
        for layer_root in layer_roots
        if layer_root.exists()
        for path in layer_root.rglob("*.py")
        for violation in forbidden_layer_imports(path)
    ]

    assert violations == []


def test_domain_layer_guard_covers_absolute_relative_and_dynamic_imports(
    tmp_path: Path,
) -> None:
    samples = {
        "absolute_storage.py": "from invest_system.storage import ReleaseCacheStore\n",
        "absolute_provider.py": "import invest_system.integrations.investment_research_kb\n",
        "relative_storage.py": "from .. import storage\n",
        "relative_provider.py": "from ..integrations import investment_research_kb\n",
        "dynamic.py": "import importlib\nimportlib.import_module('invest_system.storage')\n",
    }
    for name, source in samples.items():
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        assert forbidden_layer_imports(path), name

    safe = tmp_path / "safe.py"
    safe.write_text("from invest_system.models import VerifiedKnowledgeInput\n", encoding="utf-8")
    assert forbidden_layer_imports(safe) == []
