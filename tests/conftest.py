# -*- coding: utf-8 -*-
"""测试环境前置（防泄漏）：AstrBot 的根目录默认取「当前工作目录」。

pytest 从插件根目录启动时，框架会把 ``data/cmd_config.json``（含 dashboard
口令哈希）创建到插件目录里——这不是插件数据，而是框架按 cwd 生成的副本。
这里在导入 astrbot 之前把 ``ASTRBOT_ROOT`` 指向真正的 AstrBot 根目录
（从 PYTHONPATH/sys.path 里探测），使框架数据落在正确位置。
"""

import os
import sys
from pathlib import Path


def _find_astrbot_root() -> str | None:
    for entry in sys.path:
        try:
            candidate = Path(entry or ".").resolve()
        except Exception:  # noqa: BLE001
            continue
        if (candidate / "astrbot" / "__init__.py").is_file():
            return str(candidate)
    return None


def _configure_root() -> None:
    if os.environ.get("ASTRBOT_ROOT"):
        return
    root = _find_astrbot_root()
    if root:
        os.environ["ASTRBOT_ROOT"] = root


_configure_root()
