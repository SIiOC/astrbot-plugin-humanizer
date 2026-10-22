#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容入口：实际实现在插件根目录的 ``../package_plugin.py``。

保留本文件是为了兼容 ``tools/package_plugin.py`` 这一约定路径。打包逻辑只有一份
（根目录），因为打包时会整体排除 ``tools/``，把实现放这里反而要处理"自排除"，
双份代码也容易漂移。

用法（与根目录脚本完全一致）::

    python tools/package_plugin.py --dry-run
    python tools/package_plugin.py --force
"""

from __future__ import annotations

import runpy
from pathlib import Path

_IMPL = Path(__file__).resolve().parent.parent / "package_plugin.py"

if not _IMPL.is_file():
    raise SystemExit("找不到实际实现：%s" % _IMPL)

runpy.run_path(str(_IMPL), run_name="__main__")
