#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""astrbot_plugin_wanna_be_human 打包脚本（纯标准库，无第三方依赖）。

用法::

    python package_plugin.py              # 打包到 <插件目录父目录>/dist/astrbot_plugin_wanna_be_human_v<版本>.zip
    python package_plugin.py --dry-run    # 只列出将打包的文件清单与体积，不写 zip
    python package_plugin.py --force      # 覆盖已存在的同名 zip
    python package_plugin.py --output X   # 指定输出路径（可选）

约定：

- 版本号从插件根目录 ``metadata.yaml`` 的 ``version:`` 行读取（正则，不依赖 PyYAML）；
- zip 内顶层目录固定为 ``astrbot_plugin_wanna_be_human/``（AstrBot 插件市场安装要求）；
- 输出目录默认 ``<插件目录的父目录>/dist``（本机示例：插件目录为 ``...\astrbot_plugin_wanna_be_human`` 时输出到 ``...\dist``）；
- 仅打包插件运行所需文件 + 前端源码（``webui/``），开发/测试/运行时垃圾一律排除：

  - 目录：``.git/``、``__pycache__/``、``.pytest_cache/``、``tests/``、``tools/``、``data/``、
    ``webui/node_modules/``、``webui/dist/``（任意层级的 ``node_modules`` 也排除）
  - 文件：``*.pyc`` / ``*.pyo``、``*.tmp``、``*.log``、``REFACTOR_PROGRESS.md``、``SEED_MANIFEST.json``、
    ``pages/humanizer-console.bak*``、``package_plugin.py``（本脚本自身，开发用，不随包分发）

脚本放在插件根目录而不是 ``tools/``，是为了避免"打包时排除 ``tools/`` 会把自己也排除"的自指问题。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent
PLUGIN_NAME = PLUGIN_DIR.name
DEFAULT_DIST_DIR = PLUGIN_DIR.parent / "dist"

#: 任意层级都跳过的目录名
EXCLUDE_DIR_NAMES = {".git", "__pycache__", ".pytest_cache", "node_modules"}

#: 仅在插件根目录跳过的顶层目录
EXCLUDE_TOP_DIRS = {"tests", "tools", "data", "_verify"}

#: 任意层级都跳过的文件后缀
EXCLUDE_FILE_SUFFIXES = {".pyc", ".pyo", ".tmp", ".log"}

#: 仅在插件根目录跳过的文件
EXCLUDE_TOP_FILES = {"REFACTOR_PROGRESS.md", "SEED_MANIFEST.json", "package_plugin.py"}

#: pages/humanizer-console.bak-YYYYmmdd-HHMMSS 这类旧构建备份（文件或目录）
BAK_PATTERN = re.compile(r"^pages/humanizer-console\.bak")


class PackageError(Exception):
    """打包前置条件不满足。"""


def read_version() -> str:
    """从 metadata.yaml 读取 version 字段（不依赖 PyYAML）。"""
    meta = PLUGIN_DIR / "metadata.yaml"
    if not meta.is_file():
        raise PackageError("找不到 metadata.yaml: %s" % meta)
    try:
        text = meta.read_text(encoding="utf-8")
    except UnicodeDecodeError:  # 极端情况下按 GBK 兜底
        text = meta.read_text(encoding="gbk")
    match = re.search(r"^version\s*:\s*['\"]?([0-9][^'\"\s#]*)", text, re.MULTILINE)
    if not match:
        raise PackageError("metadata.yaml 中未找到 version 字段")
    return match.group(1).strip()


def _rel_posix(path: Path) -> str:
    return path.relative_to(PLUGIN_DIR).as_posix()


def _current_console_assets() -> set[str] | None:
    """Use Vite's current manifest to omit stale assets, without deleting files.

    Also verifies that ``index.html`` and the manifest come from the same build.
    Publishing a cross-generation pair (e.g. building twice, then packaging an
    older index) would 404 the console inside the shipped package.
    """
    console = PLUGIN_DIR / "pages" / "humanizer-console"
    manifest = console / ".vite" / "manifest.json"
    if not manifest.is_file():
        return None  # Compatible with packages built before manifests were added.
    try:
        rows = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(rows, dict) or not rows:
            raise ValueError("empty manifest")
        files: set[str] = set()
        for row in rows.values():
            if not isinstance(row, dict):
                raise ValueError("invalid manifest row")
            for rel in [row.get("file"), *(row.get("css") or []), *(row.get("assets") or [])]:
                if not isinstance(rel, str) or not rel.startswith("assets/") or ".." in Path(rel).parts:
                    raise ValueError("invalid manifest path")
                target = console / rel
                if not target.is_file():
                    raise ValueError("missing asset")
                files.add(rel)
        if not files:
            raise ValueError("no assets")
        index = console / "index.html"
        if not index.is_file():
            raise ValueError("missing index")
        html = index.read_text(encoding="utf-8")
        referenced = {
            ref[len("./"):]
            for ref in re.findall(r'(?:src|href)="(\./assets/[^"]+)"', html)
        }
        missing = sorted(referenced - files)
        if missing:
            raise ValueError("index references assets outside the manifest: %s" % ", ".join(missing))
        return {"pages/humanizer-console/" + rel for rel in files}
    except (ValueError, TypeError, OSError, UnicodeError) as exc:
        raise PackageError("控制台构建清单无效，请先重新构建") from exc


def collect_files() -> tuple[list[Path], list[tuple[str, str]]]:
    """返回 (待打包文件列表, 排除项 [(相对路径, 原因)])。"""
    included: list[Path] = []
    excluded: list[tuple[str, str]] = []
    current_assets = _current_console_assets()

    for dirpath, dirnames, filenames in os.walk(PLUGIN_DIR):
        rel_dir = Path(dirpath).relative_to(PLUGIN_DIR)
        keep_dirs = []
        for name in sorted(dirnames):
            rel = (rel_dir / name) if rel_dir != Path(".") else Path(name)
            rel = rel.as_posix()
            if name in EXCLUDE_DIR_NAMES:
                excluded.append((rel + "/", "缓存/依赖目录"))
                continue
            if rel_dir == Path(".") and name in EXCLUDE_TOP_DIRS:
                excluded.append((rel + "/", "测试/工具/运行时数据目录"))
                continue
            if rel_dir.as_posix() == "webui" and name == "dist":
                excluded.append((rel + "/", "前端构建产物（已发布到 pages/）"))
                continue
            if rel == "pages/humanizer-console/.vite":
                excluded.append((rel + "/", "前端构建清单（仅打包剪枝用，不分发）"))
                continue
            keep_dirs.append(name)
        dirnames[:] = keep_dirs

        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = _rel_posix(path)
            suffix = path.suffix.lower()
            if rel.startswith("pages/humanizer-console/assets/") and current_assets is not None and rel not in current_assets:
                excluded.append((rel, "旧构建资源（保留本地，不随包分发）"))
                continue
            if name in {"events.jsonl", "writer.lock", "state.json"}:
                excluded.append((rel, "运行态成长数据（禁止分发）"))
                continue
            if suffix in EXCLUDE_FILE_SUFFIXES:
                excluded.append((rel, "缓存/临时/日志文件"))
                continue
            if rel_dir == Path(".") and name in EXCLUDE_TOP_FILES:
                excluded.append((rel, "开发用文件（不随包分发）"))
                continue
            if BAK_PATTERN.match(rel):
                excluded.append((rel, "旧构建备份"))
                continue
            included.append(path)

    included.sort(key=_rel_posix)
    return included, excluded


def format_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return "%.2f %s" % (value, unit) if unit != "B" else "%d B" % num_bytes
        value /= 1024
    return "%d B" % num_bytes


def print_file_list(files: list[Path]) -> None:
    width = max((len(_rel_posix(p)) for p in files), default=10)
    for path in files:
        rel = _rel_posix(path)
        print("  %10s  %s" % (format_size(path.stat().st_size), rel))
    print("  " + "-" * (width + 14))


def print_exclusions(excluded: list[tuple[str, str]]) -> None:
    if not excluded:
        print("排除项：无")
        return
    by_reason: dict[str, list[str]] = {}
    for rel, reason in excluded:
        by_reason.setdefault(reason, []).append(rel)
    print("排除项：共 %d 项" % len(excluded))
    for reason, items in sorted(by_reason.items()):
        sample = ", ".join(items[:4])
        more = "" if len(items) <= 4 else " …（共 %d 项）" % len(items)
        print("  - %s（%d 项）：%s%s" % (reason, len(items), sample, more))


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def estimate_zip_size(files: list[Path]) -> int:
    """在内存里试压一次，返回预计的 zip 体积（不落盘，供 --dry-run 使用）。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            zf.write(path, "%s/%s" % (PLUGIN_NAME, _rel_posix(path)))
    return buffer.tell()


def build_zip(files: list[Path], output: Path) -> tuple[int, int]:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            arcname = "%s/%s" % (PLUGIN_NAME, _rel_posix(path))
            zf.write(path, arcname)
    return len(files), output.stat().st_size


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="打包 astrbot_plugin_wanna_be_human 插件（zip 顶层目录为插件名）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只列出将打包的文件与体积，不写 zip")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的同名 zip")
    parser.add_argument("--output", type=Path, default=None, help="输出 zip 路径（默认 dist/ 下按版本命名）")
    parser.add_argument(
        "--skip-scan",
        action="store_true",
        help="跳过发布前敏感扫描（仅排障用；正常发布不要加）",
    )
    return parser.parse_args(argv)


def _scan_findings() -> list[dict]:
    """调用 tools/pre_release_scan.py 扫描打包清单（v4.3.0 打包门禁）。"""
    tools_dir = PLUGIN_DIR / "tools"
    sys.path.insert(0, str(tools_dir))
    module = importlib.import_module("pre_release_scan")
    return module.scan_release_files(PLUGIN_DIR)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        version = read_version()
    except PackageError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2

    output = args.output.resolve() if args.output else DEFAULT_DIST_DIR / (
        "%s_v%s.zip" % (PLUGIN_NAME, version)
    )
    files, excluded = collect_files()
    total = sum(p.stat().st_size for p in files)

    print("插件目录 : %s" % PLUGIN_DIR)
    print("插件名   : %s" % PLUGIN_NAME)
    print("版本号   : %s（metadata.yaml）" % version)
    print("输出路径 : %s" % output)
    print("模式     : %s" % ("DRY-RUN（不写文件）" if args.dry_run else "打包"))
    print("-" * 72)
    print("将打包 %d 个文件，总计 %s（zip 压缩后会更小）" % (len(files), format_size(total)))
    print("-" * 72)
    print_file_list(files)
    print("-" * 72)
    print_exclusions(excluded)

    if not args.skip_scan:
        try:
            findings = _scan_findings()
        except Exception as exc:  # noqa: BLE001
            print("错误：发布前扫描失败：%s" % exc, file=sys.stderr)
            return 2
        if findings:
            print(
                "\n错误：发布前扫描发现 %d 处可疑内容，拒绝打包：" % len(findings),
                file=sys.stderr,
            )
            for item in findings[:20]:
                loc = item["path"] + (
                    ":%s" % item["line"] if item.get("line") else ""
                )
                print("  - %s: %s  %s" % (item["kind"], loc, item["excerpt"]), file=sys.stderr)
            print("修正后重跑；仅排障时可加 --skip-scan。", file=sys.stderr)
            return 3
        print("发布前扫描：0 处可疑内容")

    if not files:
        print("错误：没有可打包的文件", file=sys.stderr)
        return 2

    if args.dry_run:
        print("预计 zip 体积：%s（内存试压，未落盘）" % format_size(estimate_zip_size(files)))
        print()
        print("[DRY-RUN] 未写入任何文件。去掉 --dry-run 才会打包；目标已存在时需加 --force。")
        return 0

    if output.exists() and not args.force:
        print(
            "\n错误：目标已存在：%s\n如需覆盖请加 --force" % output,
            file=sys.stderr,
        )
        return 2

    count, zip_size = build_zip(files, output)
    print("\n完成：%d 个文件 → %s（%s）" % (count, output, format_size(zip_size)))
    print("SHA256: %s" % sha256_of(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
