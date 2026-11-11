# -*- coding: utf-8 -*-
"""测试环境路径探测（v4.2.0）。

用途：让测试在「工作副本」与「live 安装目录」两种路径层级下都能找到
真正安装的 AstrBot 框架文件，而不是按相对目录猜路径（历史上工作副本会因此
skip 掉框架补丁自检，live 才跑全）。

优先级：``ASTRBOT_ROOT`` 环境变量 → ``sys.path`` 中的 astrbot 包 → 已导入的
``astrbot`` 包位置。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def astrbot_root() -> Path | None:
    """返回 AstrBot 根目录（包含 astrbot/ 包的那一层），找不到返回 None。"""
    env = os.environ.get("ASTRBOT_ROOT")
    if env:
        candidate = Path(env)
        if (candidate / "astrbot" / "__init__.py").is_file():
            return candidate
    for entry in sys.path:
        try:
            candidate = Path(entry or ".").resolve()
        except Exception:  # noqa: BLE001
            continue
        if (candidate / "astrbot" / "__init__.py").is_file():
            return candidate
    try:
        import astrbot  # noqa: PLC0415

        return Path(astrbot.__file__).resolve().parent.parent
    except Exception:  # noqa: BLE001
        return None


def framework_file(*parts: str) -> Path | None:
    """在 AstrBot 根目录下定位一个框架文件；不存在返回 None。"""
    root = astrbot_root()
    if root is None:
        return None
    candidate = root.joinpath(*parts)
    return candidate if candidate.is_file() else None


def dashboard_assets_dir() -> Path | None:
    """AstrBot dashboard 的 dist/assets 目录；未构建/未安装时返回 None。"""
    root = astrbot_root()
    if root is None:
        return None
    candidate = root / "data" / "dist" / "assets"
    return candidate if candidate.is_dir() else None
