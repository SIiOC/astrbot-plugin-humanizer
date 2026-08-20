#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建插件内置基础语料池 corpora/base.jsonl。

数据来源（均为开源/公开语料）：
- LCCC-base（清华清洗版中文对话，MIT，覆盖微博/贴吧/青云等来源的清洗合并）
  https://huggingface.co/datasets/silver/lccc
- 豆瓣多轮对话（MultiTurnResponseSelection，论文开源数据）
  https://github.com/MarkWuNLP/MultiTurnResponseSelection
- 影视字幕对白（dgk_lost_conv 镜像）
  https://github.com/icewwn/dgk_lost_conv
- chatterbot-corpus 中文（MIT）
  https://github.com/gunthercox/chatterbot-corpus

用法：
    python tools/build_base_corpus.py [--out corpora/base.jsonl] [--total 3000]
           [--seed 42] [--weights lccc:0.5,douban:0.2,subtitle:0.2,chatterbot:0.1]

输出格式：每行一个 JSON 对象 {"role": "user"|"assistant", "content": "..."}，
user/assistant 两行交替组成一个问答对。
纯标准库实现，无第三方依赖，可复现（固定种子 + 固定输入）。
"""

import argparse
import gzip
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter

# ---------------------------------------------------------------- 过滤规则 --

# 广告/营销/低质噪声词
_AD_WORDS = [
    "加我微信", "加微信", "微信号", "代购", "刷单", "兼职", "优惠券", "秒杀",
    "包邮", "免费领取", "点击链接", "扫码", "加群", "群号", "推广", "广告",
    "淘宝", "天猫", "京东自营", "拼多多", "直播带货", "粉丝群", "关注我",
    "私信我", "看主页", "置顶", "抢购", "限时", "转发抽奖", "抽奖", "中奖",
]
# 不雅词表（基础过滤，覆盖常见）
_BAD_WORDS = [
    "妈的", "他妈的", "草泥马", "傻逼", "傻b", "煞笔", "尼玛", "去死",
    "操你", "操你妈", "肏", "fuck", "shit", "贱人", "婊子", "鸡巴",
    "逼", "狗日的", "王八蛋", "龟儿子", "智障", "白痴", "脑残", "弱智",
]
# URL / 联系方式 / 杂项噪声
_URL_RE = re.compile(r"(https?://|www\.)\S+", re.I)
_QQ_RE = re.compile(r"(?<!\d)[1-9]\d{4,11}(?!\d)")
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_PLACEHOLDER_RE = re.compile(r"[\[【][^\]】]{1,12}[\]】]")  # [图片] [语音] [表情] 等
_REPEAT_CHAR_RE = re.compile(r"(.)\1{7,}")  # 单字连续 8+ 次
_REPEAT_WORD_RE = re.compile(r"(.{2,4})\1{4,}")  # 词重复 5+ 次
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_LETTER_RE = re.compile(r"[A-Za-z\u4e00-\u9fff\u3400-\u4dbf]")  # 分母：字母+汉字

# 去除分词语料里的词间空格（LCCC / 豆瓣均为分词格式）
def strip_segmentation(text: str) -> str:
    return text.replace(" ", "").replace("\u3000", "")


def chinese_ratio(text: str) -> float:
    letters = len(_LETTER_RE.findall(text))
    if letters == 0:
        return 0.0
    return len(_CJK_RE.findall(text)) / letters


def is_noise(text: str) -> bool:
    """单句噪声判定。返回 True 表示该句应剔除。"""
    if not text:
        return True
    if len(text) < 4 or len(text) > 60:
        return True
    if chinese_ratio(text) < 0.6:
        return True
    if _URL_RE.search(text):
        return True
    if _QQ_RE.search(text) or _PHONE_RE.search(text):
        return True
    if _PLACEHOLDER_RE.search(text):
        return True
    if _REPEAT_CHAR_RE.search(text) or _REPEAT_WORD_RE.search(text):
        return True
    # 全标点 / 全数字 / 全 emoji
    if not _LETTER_RE.search(text):
        return True
    low = text.lower()
    for w in _AD_WORDS:
        if w in low:
            return True
    for w in _BAD_WORDS:
        if w in low:
            return True
    return False


def clean_sentence(text: str) -> str:
    """分词还原 + 空白整理。"""
    return strip_segmentation(text).strip()


def is_good_pair(user: str, assistant: str) -> bool:
    """整对校验：两侧都干净、且非复读。"""
    if is_noise(user) or is_noise(assistant):
        return False
    if user == assistant:
        return False
    return True


def pairs_from_turns(turns):
    """多轮对话 → 相邻问答对列表 [(user, assistant), ...]。"""
    pairs = []
    for i in range(len(turns) - 1):
        u = turns[i]
        a = turns[i + 1]
        if not u or not a:
            continue
        u = clean_sentence(u)
        a = clean_sentence(a)
        if is_good_pair(u, a):
            pairs.append((u, a))
    return pairs


# ---------------------------------------------------------------- 来源解析 --

def parse_lccc(path: str):
    """LCCC jsonl：每行一个 JSON 数组（多轮，分词格式）。
    支持截断的 gzip（如 Range 请求下载的前段）：读到坏尾时保留已解析部分。"""
    pairs = []
    if path.endswith(".gz"):
        opener = gzip.open
    else:
        opener = open
    try:
        with opener(path, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    turns = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(turns, list) or len(turns) < 2:
                    continue
                pairs.extend(pairs_from_turns(turns))
    except EOFError:
        # 截断 gzip 的坏尾：已 yield 的行已处理完，直接接受
        pass
    return pairs


def parse_douban(path: str):
    """豆瓣多轮：每行 tab 分隔，首列 label(0/1)，后续列为 utterances（分词格式）。
    只取 label=1（正样本 = 真实多轮上下文）。"""
    pairs = []
    with open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            if parts[0] != "1":
                continue
            turns = [clean_sentence(p) for p in parts[1:] if p.strip()]
            if len(turns) < 2:
                continue
            pairs.extend(pairs_from_turns(turns))
    return pairs


def parse_subtitle(path: str):
    """影视字幕：E 开头=新段落，M 开头=语句，其余行（场景说明等）跳过。"""
    pairs = []
    session = []
    with open(path, "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("E"):
                if len(session) > 1:
                    pairs.extend(pairs_from_turns(session))
                session = []
            elif line.startswith("M"):
                utter = clean_sentence(line[1:])
                if utter:
                    session.append(utter)
            # 其它行（人名/场景说明）跳过
    if len(session) > 1:
        pairs.extend(pairs_from_turns(session))
    return pairs


def parse_chatterbot_yaml(path: str):
    """chatterbot-corpus 中文 yaml：categories: / conversations: 下的一问多答块。
    手写轻量解析（不引入 yaml 依赖）。"""
    pairs = []
    with open(path, "rt", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    in_conversations = False
    current_block = []
    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("conversations:"):
            in_conversations = True
            current_block = []
            continue
        if in_conversations:
            if line.strip().startswith("- -"):  # 新对话块
                if current_block:
                    pairs.extend(pairs_from_turns(current_block))
                current_block = [line.strip()[3:].strip()]
            elif line.startswith("  - "):  # 块内条目
                current_block.append(line[4:].strip())
            elif line and not line.startswith(" ") and not line.startswith("#"):
                # 顶层新键，退出 conversations
                if current_block:
                    pairs.extend(pairs_from_turns(current_block))
                in_conversations = False
                current_block = []
    if current_block:
        pairs.extend(pairs_from_turns(current_block))
    return pairs


def parse_chatterbot_dir(path: str):
    pairs = []
    for fn in sorted(os.listdir(path)):
        if fn.endswith(".yml") or fn.endswith(".yaml"):
            pairs.extend(parse_chatterbot_yaml(os.path.join(path, fn)))
    return pairs


# ---------------------------------------------------------------- 采样输出 --

def sample_pairs(pairs_by_source, weights, total, seed):
    rng = random.Random(seed)
    # 计算每个来源应取的条数
    wsum = sum(weights.values())
    target = {src: max(0, int(total * weights[src] / wsum)) for src in weights}
    # 超出的（整除误差）摊给第一个
    diff = total - sum(target.values())
    if diff and weights:
        first = next(iter(target))
        target[first] += diff

    seen = set()
    selected = []  # (src, user, assistant)
    for src in weights:
        pairs = pairs_by_source.get(src, [])
        if not pairs:
            continue
        k = min(target.get(src, 0), len(pairs))
        rng.shuffle(pairs)
        for u, a in pairs:
            if len(selected) >= total:
                break
            if len([s for s, _, _ in selected if s == src]) >= k:
                break
            key = hashlib.md5((u + "\u0001" + a).encode("utf-8")).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            selected.append((src, u, a))
    return selected


def write_output(selected, out_path):
    rows = []
    for src, u, a in selected:
        rows.append({"role": "user", "content": u})
        rows.append({"role": "assistant", "content": a})
    with open(out_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)  # 插件根
    default_sources = {
        # 源键: [(路径, 解析函数)]
        "lccc": [
            (os.path.join(root, "tools", "data", "lccc_base_valid.jsonl.gz"), parse_lccc),
            (os.path.join(root, "tools", "data", "lccc_base_test.jsonl.gz"), parse_lccc),
            (os.path.join(root, "tools", "data", "lccc_base_train.head.jsonl.gz"), parse_lccc),
        ],
        "douban": [
            (os.path.join(root, "tools", "data", "douban_test.txt"), parse_douban),
        ],
        "subtitle": [
            (os.path.join(root, "tools", "data", "subtitle", "fanzxl.conv"), parse_subtitle),
            (os.path.join(root, "tools", "data", "subtitle", "fk24.conv"), parse_subtitle),
            (os.path.join(root, "tools", "data", "subtitle", "haosys.conv"), parse_subtitle),
            (os.path.join(root, "tools", "data", "subtitle", "juemds.conv"), parse_subtitle),
            (os.path.join(root, "tools", "data", "subtitle", "laoyj.conv"), parse_subtitle),
            (os.path.join(root, "tools", "data", "subtitle", "lost.conv"), parse_subtitle),
            (os.path.join(root, "tools", "data", "subtitle", "prisonb.conv"), parse_subtitle),
        ],
        "chatterbot": [
            (os.path.join(root, "tools", "data", "chatterbot_chinese"), parse_chatterbot_dir),
        ],
    }

    ap = argparse.ArgumentParser(description="构建内置基础语料池")
    ap.add_argument("--out", default=os.path.join(root, "corpora", "base.jsonl"))
    ap.add_argument("--total", type=int, default=3000, help="目标问答对数")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--weights", default="lccc:0.5,douban:0.15,subtitle:0.25,chatterbot:0.1",
                    help="来源权重，逗号分隔 src:weight")
    args = ap.parse_args()

    weights = {}
    for item in args.weights.split(","):
        if ":" in item:
            k, v = item.split(":", 1)
            weights[k.strip()] = float(v)

    pairs_by_source = {}
    for src, files in default_sources.items():
        if src not in weights:
            continue
        total_pairs = 0
        for path, parser in files:
            if os.path.exists(path):
                try:
                    n = parser(path)
                    total_pairs += len(n)
                    print(f"  [parse] {src}: {os.path.basename(path)} -> {len(n)} pairs")
                except Exception as e:
                    print(f"  [warn] {src}: {os.path.basename(path)} failed: {e}")
            else:
                print(f"  [skip] {src}: 缺少 {os.path.basename(path)}")
        # 合并各文件
        merged = []
        for path, parser in files:
            if os.path.exists(path):
                try:
                    merged.extend(parser(path))
                except Exception:
                    pass
        pairs_by_source[src] = merged
        print(f"[source] {src}: 共 {len(merged)} pairs")

    selected = sample_pairs(pairs_by_source, weights, args.total, args.seed)
    # 统计
    src_counter = Counter(s for s, _, _ in selected)
    n_rows = write_output(selected, args.out)
    print(f"\n[out] {args.out}: {n_rows} 行（{len(selected)} 个问答对）")
    print(f"[dist] {dict(src_counter)}")
    # 抽样展示
    rng = random.Random(args.seed)
    print("\n[抽查 10 对]")
    for s, u, a in rng.sample(selected, min(10, len(selected))):
        print(f"  [{s}] {u} / {a}")


if __name__ == "__main__":
    main()
