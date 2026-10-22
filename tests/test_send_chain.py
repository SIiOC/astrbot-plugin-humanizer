# -*- coding: utf-8 -*-
"""v3.6.0 审查修复的源码契约测试（回归钉）：纯文本回复必须走消息链。

缺陷（2026-09-06 全面审查实证，框架 4.27.4）：裸 str 传入 event.send 时，
aiocqhttp 适配器的 _parse_onebot_json 迭代 message_chain.chain 得到单个
字符并调用 str.toDict() → AttributeError（venv 内实测复现）。修复前的
57 处 `await event.send("...")` 命令回复在该框架上全部会静默失败。

契约（main.py）：
- 存在模块级 `_plain_chain(text)` 助手；
- 任何 `*.send(...)` 调用的唯一参数都不允许是纯字符串表达式
  （str 常量 / f-string / 三元 / % 或 + 拼接 / str.join）——必须经
  _plain_chain 或消息链构造。

不 import main.py（本机无 astrbot 包），用 ast 直接钉源码结构。
"""

import ast
import os
import unittest
import sys as _sys

_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ast_helpers import parse_main as _parse


def _is_pure_str(node):
    """参数表达式是否必然求值为 str（会触发适配器 AttributeError）。"""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.JoinedStr):  # f-string
        return True
    if isinstance(node, ast.IfExp):
        return _is_pure_str(node.body) and _is_pure_str(node.orelse)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
        return _is_pure_str(node.left) and _is_pure_str(node.right)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "join"
    ):
        return True
    return False


def _bare_str_sends(tree):
    out = []
    for n in ast.walk(tree):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "send"
            and not n.keywords
            and len(n.args) == 1
            and _is_pure_str(n.args[0])
        ):
            out.append(n)
    return out


class TestPlainChainHelper(unittest.TestCase):
    def test_helper_defined(self):
        found = any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_plain_chain"
            for n in ast.walk(_parse())
        )
        self.assertTrue(found, "main.py 缺少模块级 _plain_chain 助手")


class TestNoBareStrSend(unittest.TestCase):
    def test_zero_bare_str_sends(self):
        bad = _bare_str_sends(_parse())
        self.assertEqual(
            len(bad),
            0,
            "发现裸字符串 send 调用（aiocqhttp 上会 AttributeError）："
            + ", ".join(f"L{n.lineno}" for n in bad),
        )

    def test_plain_chain_actually_used(self):
        tree = _parse()
        used = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_plain_chain"
            for n in ast.walk(tree)
        )
        self.assertTrue(used, "_plain_chain 已定义但没有任何调用点（修复被回退？）")


if __name__ == "__main__":
    unittest.main()
