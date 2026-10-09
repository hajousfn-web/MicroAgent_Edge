"""Lightweight Python AST summary and function call graph builder."""
from __future__ import annotations
import ast
from dataclasses import dataclass

@dataclass(frozen=True)
class CodeGraph:
    functions: tuple[str, ...]
    calls: tuple[tuple[str, str], ...]
    imports: tuple[str, ...]

def build_code_graph(source: str) -> CodeGraph:
    """Extract functions, direct calls, and imports without executing source."""
    tree = ast.parse(source)
    functions: list[str] = []
    calls: list[tuple[str, str]] = []
    imports: list[str] = []
    def visit_scope(nodes: list[ast.stmt], scope: str) -> None:
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f'{scope}.{node.name}' if scope else node.name
                functions.append(name)
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        target = child.func.id if isinstance(child.func, ast.Name) else child.func.attr if isinstance(child.func, ast.Attribute) else '<dynamic>'
                        calls.append((name, target))
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or '')
            elif isinstance(node, ast.ClassDef):
                visit_scope(node.body, node.name)
    visit_scope(tree.body, '')
    return CodeGraph(tuple(functions), tuple(calls), tuple(imports))
