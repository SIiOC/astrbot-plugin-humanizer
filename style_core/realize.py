# -*- coding: utf-8 -*-
"""极轻量的「风格实现层」：只做句尾标点/语气词，不改写内容。

背景：v4.9.4–v4.9.6 把「平均 20.6 字、省略号 43%、语气词 47%」写进 prompt，
模型确实把句长降到了 21–23 字，但省略号/语气词仍为 0——说明模型只学会了
长度，没学会停顿。这个模块在生成后只做两件确定性、可回滚的小事：

1. 把句尾「。」按目标比例改成「……」（省略号）；
2. 在没有省略号的短句句尾补一个目标语气词（啊/哦/啦）。

不做的：不改写词句、不增减事实、不处理问句/感叹句、不碰代码/列表/链接/
多行文本；每条回复最多改一处；同一条回复多次调用结果不变（幂等）。
"""

from __future__ import annotations

import hashlib

# 只用于陈述句句尾的安全语气词；「呢/吧/吗」会改变疑问/祈使语气，不自动加。
_SAFE_PARTICLES = ("啊", "哦", "啦", "呀")
# 已出现在句尾的语气词/语气标记：出现这些就不要再补，否则会叠成「吧哦」「呀啦」。
# v4.11.1 补齐「吧/吗/哈/咯/嘞/呐/喔/噢/嘿/咧」等常见句尾，并对**最后一个字符**
# 判断，避免句中语气词把整句误判成「已经有语气词」。
_FINAL_PARTICLES = "呢啦嘛哦呗呀啊吧吗哈咯嘞呐喔噢嘿咧嗯唔诶"
_PARTICLE_CHARS = _FINAL_PARTICLES


def _ends_with_particle(body: str) -> bool:
    return bool(body) and body[-1] in _FINAL_PARTICLES


def _bucket(text: str, salt: str = "") -> int:
    """0–99 的稳定分桶（不用 Python hash，跨进程一致）。"""
    digest = hashlib.sha256((salt + "\u0001" + text).encode("utf-8")).digest()
    return int.from_bytes(digest[:2], "big") % 100


def _eligible(text: str) -> bool:
    if not text or len(text) > 60:
        return False
    stripped = text.strip()
    if not stripped or "\n" in stripped:
        return False
    if "```" in stripped or "http://" in stripped or "https://" in stripped:
        return False
    # 只实现陈述句的句尾；问句/感叹句/省略号/无标点一律不动。
    return stripped.endswith("。")


def realize_style(text: str, fingerprint: dict | None) -> str:
    """按指纹目标做一次句尾风格实现；不满足条件原样返回。"""
    if not isinstance(fingerprint, dict):
        return text
    try:
        sample = int(fingerprint.get("sample_size") or 0)
    except (TypeError, ValueError):
        return text
    if sample < 20 or not _eligible(text):
        return text

    # 只在档案确实偏好省略号/语气词时生效，避免对普通风格强加。
    try:
        target_ellipsis = float(fingerprint.get("ellipsis_ratio") or 0)
        target_particle = float(fingerprint.get("particle_ratio") or 0)
    except (TypeError, ValueError):
        return text
    if target_ellipsis < 0.25 and target_particle < 0.30:
        return text

    stripped = text.rstrip()
    ending = "。" if stripped.endswith("。") else ""
    if not ending:
        return text
    body = stripped[:-1]

    # 1) 省略号：按目标比例把句尾句号变成省略号；已带省略号/句尾语气词则跳过。
    #    v4.9.9：允许句中已有语气词（「啊，今天有点累」）仍得到省略号；
    #    但句尾已经是「啊/呢/吧」时不改，否则会变成「……啊。」且破坏幂等。
    ends_with_particle = _ends_with_particle(body)
    if (
        target_ellipsis >= 0.25
        and "……" not in body
        and "..." not in body
        and not ends_with_particle
    ):
        if _bucket(stripped, "ellipsis") < min(35, round(target_ellipsis * 70)):
            return body + "……"

    # 2) 语气词：只补在仍以句号结尾、且没有语气词的短陈述句上；
    #    比例按「剩余句子」实现，避免和省略号叠加成「……啊。」。
    if target_particle >= 0.30 and not _ends_with_particle(body):
        # 目标 47% 是「每条消息」的比例；这里只能落在没被省略号占用的句子上，
        # 所以对剩余句子略微提高概率（×1.25），整体才接近用户语料。
        particle_pct = min(65, round(target_particle * 125))
        if _bucket(stripped, "particle") < particle_pct:
            particle = _SAFE_PARTICLES[
                _bucket(stripped, "which") % len(_SAFE_PARTICLES)
            ]
            return body + particle + "。"

    return text


def should_short_bubble(text: str, fingerprint: dict | None) -> bool:
    """v4.9.11：是否把这条短回复拆成两条短气泡。

    只做“拆条”，不改内容：13–30 字的单段回复里，按目标短句比例（8%）
    选一部分，交给发送侧用更低的拆分阈值切成两条；两条拼起来与原文
    完全一致。用于补足模型从不输出 <10 字短句的结构性缺口。
    """
    if not isinstance(fingerprint, dict) or not text:
        return False
    try:
        sample = int(fingerprint.get("sample_size") or 0)
        short_target = float(fingerprint.get("short_ratio") or 0)
    except (TypeError, ValueError):
        return False
    if sample < 20 or short_target < 0.08:
        return False
    stripped = text.strip()
    if not (13 <= len(stripped) <= 30):
        return False
    if "\n" in stripped or "```" in stripped or "http" in stripped:
        return False
    return _bucket(stripped, "short_bubble") < 25


_QUESTION_SUFFIXES = ("你呢？", "你说呢？", "对吧？", "是不是？")


def realize_question(text: str, fingerprint: dict | None) -> str:
    """v4.9.13：少量陈述句末尾补一个反问，补足「问句占比」维度。

    只对 8–60 字、以「。」或「……」收尾、无代码/链接/换行的陈述句生效；
    按目标问句比例低概率追加一句通用反问（你呢/你说呢/对吧/是不是）。
    已经是问句、感叹句、过长文本一律不动；二次调用不会叠加。
    """
    if not isinstance(fingerprint, dict) or not text:
        return text
    try:
        sample = int(fingerprint.get("sample_size") or 0)
        question_target = float(fingerprint.get("question_ratio") or 0)
    except (TypeError, ValueError):
        return text
    if sample < 20 or question_target < 0.08:
        return text
    stripped = text.strip()
    if not (8 <= len(stripped) <= 60):
        return text
    if "？" in stripped or "?" in stripped or "\n" in stripped:
        return text
    if "```" in stripped or "http" in stripped:
        return text
    if stripped.endswith("！") or stripped.endswith("!"):
        return text
    if not (stripped.endswith("。") or stripped.endswith("……")):
        return text
    pct = min(30, round(question_target * 130))
    if _bucket(stripped, "question") >= pct:
        return text
    body = stripped[:-1] if stripped.endswith("。") else stripped
    suffix = _QUESTION_SUFFIXES[_bucket(stripped, "which_q") % len(_QUESTION_SUFFIXES)]
    return body + suffix

