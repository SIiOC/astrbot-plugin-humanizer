# -*- coding: utf-8 -*-
"""
复读拦截（纯逻辑层）。

背景（2026-09-06 日志实证，当天 5 对样本）：agent 模式下模型先调
send_message_to_user 把回复发一遍，agent 循环继续后又生成一段内容几乎
相同的「最终回复」，由 RespondStage 再次发出——QQ 侧收到两条复读。
框架 respond 阶段已有「待发文本 in 已发文本列表」的原生防护，但匹配是
strip 后逐字相等，只差一个尾句号/空格就漏（当天 3/5 对属于此类）。

本模块在归一化（去空白/标点/emoji、转小写）后做三重判定：
1. 单条相似：与任一已发文本 SequenceMatcher ratio >= 阈值；
2. 包含：待发文本包含某条已发文本（改写+追加型），或被其包含；
3. 拼接：模型分段发送后把全文拼着重发（与已发文本的拼接串互含）。

判定方向：宁漏勿误杀——异常、低置信、过短文本一律放行，最坏退化为
现状（漏拦），绝不吞正常回复。真实样本校准记录：
- 命中：同文+尾句号（ratio=1.0）、同文+句中空格（1.0）、一字之差改写（~0.83）
- 放行：强改写有增量型（"瑞幸9.9安排上"→"9块9的冰美式直接安排"，~0.14，
  有新信息，非复读）
"""

import re
from difflib import SequenceMatcher

# 归一化：中文属 Unicode 字母类会被 \w 保留，空白/标点/emoji 落入 \W 被去除。
_NORM_RE = re.compile(r"[\s\W_]+", re.UNICODE)

# 待发文本归一化后短于该长度不判——过短的高相似（"好呀宝"类寒暄）误杀面大。
MIN_NORM_LEN = 8


def normalize(text: str) -> str:
    """归一化：去除空白、标点、emoji 与下划线后转小写。"""
    return _NORM_RE.sub("", text or "").lower()


def match_sent_text(text: str, sent_texts, threshold: float) -> float:
    """判定待发文本是否复读本轮回合已发内容。

    Args:
        text: 待发送的最终回复全文（消息链上所有 Plain 拼接）。
        sent_texts: 框架 v20260831 补丁登记在
            ``_send_message_to_user_current_session_plain_texts`` 的本轮
            已发纯文本列表（strip 后）。
        threshold: 单条相似度判定阈值（0~1），实测 0.82 可拦一字之差
            的 12 字短句且距正常"另说一段"场景（<0.6）有充足间隔。

    Returns:
        命中时的相似度分数（用于日志），未命中返回 0.0。
    """
    if not sent_texts or not isinstance(sent_texts, (list, tuple)):
        return 0.0
    a = normalize(text)
    if len(a) < MIN_NORM_LEN:
        return 0.0

    norms = [n for n in (normalize(s) for s in sent_texts) if n]
    if not norms:
        return 0.0

    # 判定 3（拼接）：分段发送后全文拼着重发；顺带覆盖待发内容已是
    # 已发内容子集的情形（respond 只复读其中一段）。
    joined = "".join(norms)
    if len(joined) >= MIN_NORM_LEN and (joined in a or a in joined):
        return 1.0

    best = 0.0
    for b in norms:
        # 判定 2（包含）：改写+追加型——待发文本已含某条已发全文。
        if len(b) >= MIN_NORM_LEN and (a.startswith(b) or b in a):
            return 1.0
        # 判定 1（相似）：改写型复读。autojunk=False：默认值在长文本上
        # 会把高频字当 junk 导致 ratio 失真。
        r = SequenceMatcher(None, a, b, autojunk=False).ratio()
        if r > best:
            best = r
    return best if best >= threshold else 0.0
