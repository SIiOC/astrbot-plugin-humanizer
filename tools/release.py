#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键发布前门禁（v4.3.0，纯标准库）。

顺序：pytest → 打包清单敏感扫描 → git 历史报告 → 打包 zip → 输出 SHA256。
**不执行 git commit / push / 部署**，这些仍由人工按发布流程执行。

用法::

    python tools/release.py                 # 全流程
    python tools/release.py --skip-tests    # 已跑过测试时
    python tools/release.py --dry-run       # 只做扫描与展示，不打包
    python tools/release.py --strict-history # git 历史命中即失败（默认只报告）

退出码：0=通过；1=测试/扫描/打包失败；2=运行错误。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = PLUGIN_ROOT / "tools"


def _scanner():
    sys.path.insert(0, str(TOOLS_DIR))
    return importlib.import_module("pre_release_scan")


def _run(cmd: list[str]) -> int:
    print("+ " + " ".join(cmd))
    return subprocess.call(cmd, cwd=str(PLUGIN_ROOT))


def _print_findings(title: str, findings: list[dict], limit: int = 20) -> None:
    print(f"[release] {title}：{len(findings)} 处")
    for item in findings[:limit]:
        loc = item["path"] + (f":{item['line']}" if item.get("line") else "")
        print(f"  - {item['kind']}: {loc}  {item['excerpt']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Humanizer 一键发布前门禁")
    parser.add_argument("--skip-tests", action="store_true", help="跳过 pytest（已单独跑过时）")
    parser.add_argument("--dry-run", action="store_true", help="只扫描与展示，不打包")
    parser.add_argument("--strict-history", action="store_true", help="git 历史命中即失败")
    parser.add_argument("--git-limit", type=int, default=100, help="git 历史扫描提交数")
    args = parser.parse_args(argv)

    if not args.skip_tests:
        # v4.6.0：AstrBot venv 可能被重建（pytest 丢失）；提前给出可执行的补装命令
        if importlib.util.find_spec("pytest") is None:
            print(
                "[release] 缺少 pytest（venv 可能被重建）。补装：\n"
                f'  uv pip install --python "{sys.executable}" -r requirements-dev.txt',
                file=sys.stderr,
            )
            return 2
        code = _run([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"])
        if code != 0:
            print("[release] 失败：pytest 未通过", file=sys.stderr)
            return 1

    try:
        scanner = _scanner()
        findings = scanner.scan_release_files(PLUGIN_ROOT)
    except Exception as exc:  # noqa: BLE001
        print(f"[release] 运行失败：发布扫描器不可用：{exc}", file=sys.stderr)
        return 2
    _print_findings("打包清单敏感扫描", findings)
    if findings:
        print("[release] 失败：打包清单存在可疑内容（修复后重跑）", file=sys.stderr)
        return 1

    history_findings = []
    try:
        history_findings = scanner.scan_git_history(PLUGIN_ROOT, args.git_limit)
    except Exception as exc:  # noqa: BLE001
        print(f"[release] 提示：git 历史扫描跳过（{exc}）")
    if history_findings:
        _print_findings("git 历史报告（旧提交无法通过改工作树消除）", history_findings)
        if args.strict_history:
            print("[release] 失败：--strict-history 下历史命中即阻断", file=sys.stderr)
            return 1
        print("[release] 历史命中不阻断本次发布（如需清理需重写历史）")

    if args.dry_run:
        print("[release] DRY-RUN：扫描通过，未打包。")
        return 0

    code = _run([sys.executable, str(PLUGIN_ROOT / "package_plugin.py"), "--force"])
    if code != 0:
        print("[release] 失败：打包未通过（参见上方输出）", file=sys.stderr)
        return 1

    metadata = (PLUGIN_ROOT / "metadata.yaml").read_text(encoding="utf-8")
    version = ""
    for line in metadata.splitlines():
        if line.startswith("version:"):
            version = line.split(":", 1)[1].strip().strip("'\"")
            break
    zip_path = PLUGIN_ROOT.parent / "dist" / f"astrbot_plugin_wanna_be_human_v{version}.zip"
    if not zip_path.is_file():
        print(f"[release] 失败：未找到产物 {zip_path}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    print(f"[release] 完成：v{version}")
    print(f"[release] 产物：{zip_path}")
    print(f"[release] 体积：{zip_path.stat().st_size} B")
    print(f"[release] SHA256：{digest}")
    print("[release] 下一步（人工）：git add/commit/tag → push → 市场提交 → 备份后同步 live。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
