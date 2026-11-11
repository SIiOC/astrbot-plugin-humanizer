#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布前敏感内容扫描（v4.2.0，纯标准库）。

在打 zip / 推送 / 提交市场之前，检查「将要发布的内容」是否意外带入：
- 本机绝对路径（``C:\\Users\\...``、``E:\\ai\\...`` 等）
- 凭据/密钥（GitHub token、AWS key、私钥头、``sk-`` API key）
- 运行时数据与私人语料（``data/``、``user_corpus.jsonl``、``stats.json`` 等）
- 打包策略排除项（``tests/``、``tools/``、``node_modules/``）混入 zip

默认扫描 ``package_plugin.collect_files()`` 的打包清单——与真正发布的文件
完全一致；也可直接扫描已有 zip（``--zip``）。

用法::

    python tools/pre_release_scan.py
    python tools/pre_release_scan.py --zip dist/astrbot_plugin_wanna_be_human_v4.2.0.zip
    python tools/pre_release_scan.py --json

退出码：0=干净；1=发现可疑内容；2=运行错误。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

#: 盘符绝对路径（如 E:\ai\... / C:/Users/...）
ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/][^\s\"'`<>|]*")
#: 用户主目录路径
HOME_PATH = re.compile(r"(?:C:[\\/]Users[\\/]|/home/[^/\s\"']+/|~/\.)")
#: 凭据/密钥特征
SECRET_PATTERNS = (
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("api_key_sk", re.compile(r"\bsk-[A-Za-z0-9]{24,}")),
)

#: zip 中不应出现的目录（相对包内路径）
FORBIDDEN_ZIP_DIRS = (
    "tests/",
    "tools/",
    "data/",
    "node_modules/",
    ".git/",
    ".pytest_cache/",
)
#: zip 中不应出现的文件（运行态/开发用）
FORBIDDEN_ZIP_NAMES = (
    "SEED_MANIFEST.json",
    "REFACTOR_PROGRESS.md",
    "package_plugin.py",
    ".env",
    "user_corpus.jsonl",
    "stats.json",
    "proactive_state.json",
    "time_state.json",
    "cmd_config.json",
)
#: 只对这些后缀做文本扫描（其余按二进制跳过，避免噪声）
TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".toml",
    ".cfg", ".ini", ".html", ".css", ".js", ".mjs", ".ts", ".vue",
    ".sh", ".ps1", ".bat", ".gitignore", ".dockerfile",
}

#: git 历史里只关心「运行时数据/凭据」——tests/tools 等仓库正常内容不算
HISTORY_FORBIDDEN_DIRS = ("data/", ".pytest_cache/")
HISTORY_FORBIDDEN_NAMES = (
    ".env",
    "user_corpus.jsonl",
    "stats.json",
    "proactive_state.json",
    "time_state.json",
    "persona_state.json",
    "cmd_config.json",
)


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _excerpt(text: str, start: int, end: int, kind: str) -> str:
    """截取命中片段；凭据类只保留前缀，避免把密钥原文打进日志。"""
    raw = text[start:end].strip().replace("\n", " ")
    if kind in {"github_token", "github_pat", "aws_access_key", "api_key_sk"}:
        return raw[:6] + "…（已脱敏）"
    return raw[:120]


def scan_text(name: str, text: str) -> list[dict]:
    """扫描一段文本，返回命中列表（纯函数，便于单测）。"""
    findings: list[dict] = []
    for kind, pattern in (("absolute_path", ABSOLUTE_PATH), ("home_path", HOME_PATH)):
        for match in pattern.finditer(text):
            findings.append(
                {
                    "path": name,
                    "line": _line_of(text, match.start()),
                    "kind": kind,
                    "excerpt": _excerpt(text, match.start(), match.end(), kind),
                }
            )
    for kind, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(
                {
                    "path": name,
                    "line": _line_of(text, match.start()),
                    "kind": kind,
                    "excerpt": _excerpt(text, match.start(), match.end(), kind),
                }
            )
    return findings


def scan_file(path: Path, name: str | None = None) -> list[dict]:
    """扫描一个文本文件；二进制/不可解码文件跳过。"""
    display = name or str(path)
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
        "LICENSE",
        ".gitignore",
    }:
        return []
    try:
        if path.stat().st_size > 5 * 1024 * 1024:
            return []
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return scan_text(display, text)


def scan_release_files(root: Path | None = None) -> list[dict]:
    """扫描 package_plugin 的打包清单（默认插件根目录）。"""
    base = Path(root) if root else PLUGIN_ROOT
    sys.path.insert(0, str(base))
    try:
        import package_plugin  # noqa: PLC0415 —— 延迟导入，避免被当作运行依赖
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"无法导入 package_plugin（{base}）: {exc}") from exc
    files, _excluded = package_plugin.collect_files()
    findings: list[dict] = []
    for path in files:
        rel = path.relative_to(base).as_posix()
        findings.extend(scan_file(path, rel))
    return findings


def _zip_name_is_forbidden(name: str) -> str | None:
    posix = name.replace("\\", "/")
    if any(f"/{d}" in f"/{posix}" or posix.startswith(d) for d in FORBIDDEN_ZIP_DIRS):
        return "forbidden_dir"
    base = posix.rsplit("/", 1)[-1]
    if base in FORBIDDEN_ZIP_NAMES:
        return "forbidden_file"
    return None


def _history_path_is_forbidden(name: str) -> bool:
    posix = name.replace("\\", "/")
    if any(posix.startswith(d) or f"/{d}" in f"/{posix}" for d in HISTORY_FORBIDDEN_DIRS):
        return True
    return posix.rsplit("/", 1)[-1] in HISTORY_FORBIDDEN_NAMES


def scan_zip(zip_path: Path, expected_top: str = "astrbot_plugin_wanna_be_human/") -> list[dict]:
    """扫描一个发布 zip：路径策略 + 文本内容。"""
    findings: list[dict] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            kind = _zip_name_is_forbidden(name)
            if kind:
                findings.append(
                    {
                        "path": name,
                        "line": None,
                        "kind": kind,
                        "excerpt": "发布包不应包含该路径（打包排除规则失效）",
                    }
                )
            if expected_top and not name.startswith(expected_top):
                findings.append(
                    {
                        "path": name,
                        "line": None,
                        "kind": "top_dir_mismatch",
                        "excerpt": f"顶层目录应为 {expected_top}",
                    }
                )
            suffix = Path(name).suffix.lower()
            if suffix not in TEXT_SUFFIXES:
                continue
            try:
                if info.file_size > 5 * 1024 * 1024:
                    continue
                text = zf.read(info).decode("utf-8")
            except (UnicodeDecodeError, RuntimeError):
                continue
            findings.extend(scan_text(name, text))
    return findings


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0 and args and args[0] not in {"cat-file", "show"}:
        raise RuntimeError((result.stderr or "").strip() or f"git {args[0]} 失败")
    return result.stdout


def scan_git_history(root: Path | None = None, limit: int = 100) -> list[dict]:
    """扫描最近 ``limit`` 个提交的内容（含已被删除的文件）。

    历史里的敏感内容无法通过改工作树消除，通常作为「报告项」而非阻塞项：
    发布脚本默认报告、``--strict-history`` 才阻断发布。
    """
    base = Path(root) if root else PLUGIN_ROOT
    try:
        commits = _git(base, "rev-list", "--all", f"--max-count={int(limit)}").split()
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 git 可执行文件") from exc
    findings: list[dict] = []
    for sha in commits:
        short = sha[:8]
        for path in _git(base, "ls-tree", "-r", "--name-only", sha).splitlines():
            path = path.strip()
            if not path:
                continue
            if _history_path_is_forbidden(path):
                findings.append(
                    {
                        "path": f"{short}:{path}",
                        "line": None,
                        "kind": "history_runtime_data",
                        "excerpt": "历史提交包含运行时数据/凭据路径（现在可能已删除）",
                    }
                )
                continue
            if Path(path).suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                size = int(_git(base, "cat-file", "-s", f"{sha}:{path}").strip() or 0)
            except ValueError:
                size = 0
            if size == 0 or size > 1024 * 1024:
                continue
            text = _git(base, "show", f"{sha}:{path}")
            if text:
                findings.extend(scan_text(f"{short}:{path}", text))
    # 同一内容会在多个提交里重复命中：按 (kind,path,line,excerpt) 去重
    seen: set[tuple] = set()
    unique: list[dict] = []
    for item in findings:
        key = (item["kind"], item["path"], item.get("line"), item["excerpt"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="发布前敏感内容扫描")
    parser.add_argument("--root", default=str(PLUGIN_ROOT), help="插件根目录（默认本脚本上级）")
    parser.add_argument("--zip", default="", help="改为扫描指定发布 zip")
    parser.add_argument(
        "--git-history",
        action="store_true",
        help="同时扫描 git 历史（含已删除文件）",
    )
    parser.add_argument("--git-limit", type=int, default=100, help="git 历史扫描提交数上限")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args(argv)

    findings: list[dict] = []
    targets: list[str] = []
    try:
        if args.zip:
            findings.extend(scan_zip(Path(args.zip)))
            targets.append(args.zip)
        else:
            findings.extend(scan_release_files(Path(args.root)))
            targets.append(f"{args.root}（打包清单）")
        if args.git_history:
            findings.extend(scan_git_history(Path(args.root), args.git_limit))
            targets.append(f"git 历史最近 {args.git_limit} 个提交")
    except Exception as exc:  # noqa: BLE001
        print(f"[pre-release-scan] 运行失败: {exc}", file=sys.stderr)
        return 2
    target = " + ".join(targets)

    if args.json:
        print(
            json.dumps(
                {"target": target, "clean": not findings, "findings": findings},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif findings:
        print(f"[pre-release-scan] 发现 {len(findings)} 处可疑内容（{target}）：")
        for item in findings:
            loc = item["path"] + (f":{item['line']}" if item.get("line") else "")
            print(f"  - {item['kind']}: {loc}  {item['excerpt']}")
        print("[pre-release-scan] 请修正后重跑；发布/推送前必须为 0 处。")
    else:
        print(f"[pre-release-scan] 干净：0 处可疑内容（{target}）")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
