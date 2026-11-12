#!/usr/bin/env python3
"""Regression tests for function-local imports that shadow module-level imports.

A function-local ``import os`` (anywhere in a function body) makes ``os`` a local
name for the whole function, so any earlier use raises UnboundLocalError. This
broke ``env:<VAR>`` password references in ``retrieve_password_secure`` and the
argument-validation error paths of the ``performance-graph`` CLI command.
"""

import ast
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

from vast_admin_mcp.cli import _cli_module as cli_module  # cli.py (the cli/ package loads it by path)
from vast_admin_mcp.utils import retrieve_password_secure


class TestEnvPasswordReference(unittest.TestCase):
    def test_env_reference_resolves(self):
        with patch.dict(os.environ, {"VAM_TEST_PASSWORD": "s3cret"}):
            self.assertEqual(
                retrieve_password_secure("cluster1", "admin", "env:VAM_TEST_PASSWORD"),
                "s3cret",
            )

    def test_missing_env_variable_raises_value_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                retrieve_password_secure("cluster1", "admin", "env:VAM_TEST_MISSING")


class TestPerformanceGraphArgumentErrors(unittest.TestCase):
    def test_missing_monitor_name_exits_cleanly(self):
        args = SimpleNamespace(debug=False, mcp=False, monitor_name=None, cluster="c1", object_name="cluster")
        with patch.object(cli_module, "logging_main"), patch("sys.stderr"):
            with self.assertRaises(SystemExit) as ctx:
                cli_module.handle_performance_graph_command(args)
        self.assertEqual(ctx.exception.code, 1)


class TestNoShadowingLocalImports(unittest.TestCase):
    """A function must not use a module-level name before re-importing it locally."""

    def test_no_use_before_local_reimport(self):
        problems = []
        for path in sorted((SRC / "vast_admin_mcp").rglob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            module_names = {
                alias.asname or alias.name.split(".")[0]
                for node in tree.body
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            }
            for func in ast.walk(tree):
                if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                first_import = {}
                for node in ast.walk(func):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        for alias in node.names:
                            name = alias.asname or alias.name.split(".")[0]
                            if name in module_names:
                                first_import[name] = min(node.lineno, first_import.get(name, node.lineno))
                for node in ast.walk(func):
                    if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                            and node.id in first_import and node.lineno < first_import[node.id]):
                        problems.append(
                            f"{path.relative_to(SRC)}:{node.lineno} {func.name}() uses '{node.id}' "
                            f"before its local import on line {first_import[node.id]}"
                        )
        problems = sorted(set(problems))
        self.assertEqual(problems, [], "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
