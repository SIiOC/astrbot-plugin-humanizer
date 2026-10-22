# -*- coding: utf-8 -*-
"""AST 契约测试共用助手（v3.5.2 收敛：原先在 7 个测试文件里各有一份样板）。

用法（各测试文件顶部）：
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _ast_helpers import find_func as _find_func, parse_main as _parse
"""

import ast
import os

_MAIN = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py"
)


def parse_main(path: str | None = None) -> ast.Module:
    """解析 main.py（或指定文件）为 AST。"""
    target = path or _MAIN
    with open(target, encoding="utf-8") as f:
        return ast.parse(f.read(), filename=target)


def find_func(tree: ast.Module, name: str):
    """按函数名取 AST 节点；找不到直接 AssertionError（契约失败）。"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"main.py 中找不到函数 {name}")
