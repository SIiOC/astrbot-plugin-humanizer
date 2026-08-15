# -*- coding: utf-8 -*-
"""
中文 AI 痕迹清理规则。

基于 Humanizer-zh（源自维基百科 "Signs of AI writing"）的 24 种模式，
只处理高置信度的机械痕迹，保守设计，避免破坏正常语义。

本模块不依赖 astrbot，纯 Python 实现，便于本地单元测试。
"""

import re

# ---------------------------------------------------------------------------
# 1. 表情符号（模式 17）
# ---------------------------------------------------------------------------
# 常见 Unicode 表情符号区段：Emoticons、杂项符号、补充符号、国旗等
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"  # 杂项符号和象形符号
    "\U0001F600-\U0001F64F"  # 表情符号
    "\U0001F680-\U0001F6FF"  # 交通和地图符号
    "\U0001F700-\U0001F77F"  # 字母符号
    "\U0001F780-\U0001F7FF"  # 几何图形扩展
    "\U0001F800-\U0001F8FF"  # 补充箭头
    "\U0001F900-\U0001F9FF"  # 补充符号和象形符号
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002702-\U000027B0"  # 装饰符号
    "\U00002600-\U000027BF"  # 杂项符号
    "\U00002B00-\U00002BFF"  # 杂项符号和箭头
    "\U0000FE00-\U0000FE0F"  # 变体选择符
    "\U0001F1E6-\U0001F1FF"  # 国旗
    "]",
    re.UNICODE,
)


def remove_emoji(text: str) -> str:
    """移除文本中的所有表情符号。"""
    return _EMOJI_RE.sub("", text)


# ---------------------------------------------------------------------------
# 2. 客套话 / 谄媚语气 / 协作交流痕迹（模式 19、21）
# ---------------------------------------------------------------------------
# 这些是 AI 对话中高频出现的"服务腔"，真人很少这么说。
# 带锚点的规则使用多行模式（re.M），覆盖多段回复中每段开头/结尾的套话。
# "您好/你好"问候语保留非多行模式：只在全文开头匹配，避免误删正文行首的问候。
_COURTESY_PATTERNS = [
    # 开头谄媚
    re.compile(r"^好问题！?\s*", re.M),
    re.compile(r"^(好的|好的呢|没问题|当然可以|当然没问题|完全可以|可以的)[！!，,。]?\s*(我来|让我|我将|我可以|我帮|我这就|以下|下面是|为您|为你|给你)", re.M),
    re.compile(r"^很高兴(为您|为你)(服务|解答|提供帮助)[！!，,。]?\s*", re.M),
    re.compile(r"^(尊敬的|亲爱的)?(用户|朋友|您好|你好)[！!，,。]?\s*"),
    # 结尾客套
    # 前缀只匹配问号：若匹配句号/空白/换行，会把前一句的句号和换行一并删掉。
    # （例如「方案可行。\n希望这对您有帮助！」会把「。」一起吞掉。）
    re.compile(r"[?？]?希望(?:以上|这些|我的|这个)?(?:回答|信息|建议|内容|说明|方案|回复|这|它)?(?:能|可以)?对?(?:您|你)?有(?:所)?帮助[！!]?\s*$", re.M),
    re.compile(r"[?？]?(如果您?有(任何)?(问题|疑问|需要|其他问题)?[，,。]?[的]?请(随时|尽管)(告诉|联系|问我|提问)?(我)?)[！!。]?\s*$", re.M),
    re.compile(r"[?？]?(如果还有其他问题[，,。]?欢迎?(随时)?(告诉|问我|联系我)?)[！!。]?\s*$", re.M),
    re.compile(r"[?？]?(祝您?[^。！!]{0,12}(愉快|顺利|好运|开心))[！!]?\s*$", re.M),
    re.compile(r"[?？]?(感谢您的(提问|阅读|关注|支持|使用))[！!]?\s*$", re.M),
    # 句中谄媚/共情过度
    re.compile(r"(我(完全)?(理解|明白)您?的(感受|想法|心情|处境)[，,。])", re.M),
    re.compile(r"(您说得(完全)?正确[！!，,。])", re.M),
    re.compile(r"(这是(一个)?(非常)?好(的)?(问题|观点)[！!，,。])", re.M),
    re.compile(r"(您的(问题|观点)(非常|很)?(好|有价值|有见地)[，,。])", re.M),
]


def _strip_courtesy(text: str) -> str:
    """去除 AI 服务腔客套话。"""
    for pat in _COURTESY_PATTERNS:
        text = pat.sub("", text)
    return text.strip()


# ---------------------------------------------------------------------------
# 3. 知识截止日期免责声明（模式 20）
# ---------------------------------------------------------------------------
# 收紧设计：每条规则都必须包含明确的免责关键词（"截止/截至"等），
# 避免像早期版本那样因"我的知识"过宽匹配而误删正常内容。
# 尾段只吞"日期/说明"这类内容：排除句读标点（防止跨句吞字），
# 并要求尾部必须有句读标点或换行收尾（防止吞掉后续正文）。
# 尾部统一为二选一：要么吃掉一个句读标点（免责声明以标点收尾），
# 要么断言紧后是句读标点/换行/结尾（无标点时避免吞掉后续正文）。
_DISCLAIMER_TAIL = r"(?:[，,。:：]\s*|(?=[，,。!！?？;；\n]|$))"

# 免责声明关键词之后只允许"数字日期"成分（如 "2024年10月"），
# 不吞任意汉字，避免把 "后无法回答" 之类的正文一并删掉。
_DISCLAIMER_DATE = r"\s*(?:是|为|到|于)?[（(]?\s*\d{1,4}\s*年?\s*\d{0,2}\s*月?\s*\d{0,2}\s*日?[）)]?"

_KNOWLEDGE_DISCLAIMERS = [
    re.compile(r"(?:根据|基于|按照)?我的知识(?:库)?(?:截止|截至)(?:日期|时间|于)?" + _DISCLAIMER_DATE + _DISCLAIMER_TAIL, re.M),
    re.compile(r"(?:根据|基于)?我的训练数据(?:库)?(?:截止|截至)" + _DISCLAIMER_DATE + _DISCLAIMER_TAIL, re.M),
    re.compile(r"(?:由于)(?:我(?:的)?)?(?:知识|训练数据)(?:截止|有限|限制)" + _DISCLAIMER_TAIL, re.M),
    re.compile(r"(?:虽然|尽管)(?:我)?(?:对)?(?:这(?:一|个)?|该|此)?(?:主题|话题|问题|信息)(?:的)?(?:了解|掌握)(?:有限|不足|不多)" + _DISCLAIMER_TAIL, re.M),
]


def _strip_disclaimers(text: str) -> str:
    """去除 AI 免责声明。"""
    for pat in _KNOWLEDGE_DISCLAIMERS:
        text = pat.sub("", text)
    return text.strip()


# ---------------------------------------------------------------------------
# 4. 填充短语 / AI 高频词（模式 7、22）
# ---------------------------------------------------------------------------
# 直接删除的句子级填充语
_FILLER_REMOVE = [
    re.compile(r"^(值得注意的是|值得一提的是|需要注意的是|请大家注意|请注意)[，,：:]?\s*"),
    re.compile(r"^(总而言之|综上所述|总的来说|总体而言|归根结底|说到底)[，,：:]?\s*"),
    re.compile(r"^(毫无疑问|毋庸置疑|不可否认)[，,：:]?\s*"),
    re.compile(r"^(首先[，,]?让我们(来)?(看看|思考|讨论|回顾))[，,：:]?\s*"),
    re.compile(r"(在(这个|当今|当前)(快节奏|日新月异|不断变化)?(的)?(时代|世界|社会|环境)中)[，,：:]?\s*"),
    re.compile(r"(在这一时间点|在这个时间点)[，,：:]?"),  # 填充短语 → 现在
]

# 词/短语替换表：AI 腔 → 更自然说法
_FILLER_REPLACE = [
    ("此外，", "另外，"),
    ("此外", "另外"),
    ("值得注意的是，", ""),
    ("在这一时间点", "现在"),
    ("在这个时间点", "现在"),
    ("由于……的事实", "因为"),
    ("不仅仅", "不只"),
]


def _strip_fillers(text: str) -> str:
    """去除填充短语并替换 AI 高频词。"""
    for pat in _FILLER_REMOVE:
        text = pat.sub("", text)
    for old, new in _FILLER_REPLACE:
        text = text.replace(old, new)
    return text.strip()


# ---------------------------------------------------------------------------
# 5. 过度限定（模式 23）
# ---------------------------------------------------------------------------
_HEDGING_RE = re.compile(r"(可能|也许|大概|或许)(可能|也许|大概|或许)")


def _strip_hedging(text: str) -> str:
    """合并连续堆叠的限定词，如"可能也许" → "可能"。"""
    prev = None
    while prev != text:
        prev = text
        text = _HEDGING_RE.sub(r"\1", text)
    return text


# ---------------------------------------------------------------------------
# 6. 破折号滥用（模式 13）
# ---------------------------------------------------------------------------
_DASH_RE = re.compile(r"——+")
# 判定"插入式"破折号：两侧紧邻的字符都必须是实际文字（非标点/空白）
_NON_PUNCT = re.compile(r"[^\s，。！？；：、,.!?;:\"'（()）【】\[\]『』「」]")
_MAX_DASH_RUN = 30  # 单条消息最多允许的破折号个数保护
# 数字区间（如 "2020——2026"、"5——10人"）：两侧都是数字，语义是区间而非插入
_NUMERIC = re.compile(r"[0-9０-９]")


def _fix_dashes(text: str) -> str:
    """处理中文破折号滥用（模式 13）。

    中文中"——"是合法标点，用途包括声音延长（"啊——"）、数字区间（"2020——2026"）、
    解释说明等，不能一律替换。仅在以下条件同时满足时收敛为逗号：
      1. 破折号出现 >= 2 次（高频）；
      2. 每个破折号两侧都是实际文字（插入式用法，如"它很快——也很稳"），
         而非句尾延长或单侧标点；
      3. 两侧不是数字区间用法（"2020——2026" 保留）。

    不满足条件时原样保留，避免误伤合法用法。
    """
    matches = list(_DASH_RE.finditer(text))
    if len(matches) < 2 or len(matches) > _MAX_DASH_RUN:
        return text
    all_insertion = True
    for m in matches:
        left = text[m.start() - 1] if m.start() > 0 else ""
        right = text[m.end()] if m.end() < len(text) else ""
        if not (_NON_PUNCT.fullmatch(left) and _NON_PUNCT.fullmatch(right)):
            all_insertion = False
            break
        if _NUMERIC.fullmatch(left) and _NUMERIC.fullmatch(right):
            # 数字区间：如 "2020——2026"，语义是区间，不是插入式破折号
            all_insertion = False
            break
    if not all_insertion:
        return text
    return _DASH_RE.sub("，", text)


# ---------------------------------------------------------------------------
# 7. 否定式排比（模式 9）—— 只处理高置信的开头结构
# ---------------------------------------------------------------------------
_NEG_CONTRAST_RE = [
    # 执行顺序注意：ZH_STAGES 中 fillers 先于 neg_contrast，「不仅仅」已被
    # _FILLER_REPLACE 替换为「不只」，因此正则按替换后的形态写（不只/不只是/不单是）。
    # 尾部不带「。?」：句末标点不属于要删的前半段，经 text[m.end():] 原样保留。
    re.compile(r"^(这|那)?(不只是|不只|不单是)[^，。]{0,30}[，,](更是|而是|而是说)([^，。]{0,40})"),
]


def _strip_neg_contrast(text: str) -> str:
    """处理"不仅仅是 X，更是 Y"式开头（AI 高频套路）。

    保守策略：命中时保留后半句（Y），删掉前半句（X），避免过度改写。
    只删「不只是X，」前半段：group(3) 连接词 + group(4) 后半句拼回，
    其后内容（含句末标点）原样保留。
    """
    for pat in _NEG_CONTRAST_RE:
        m = pat.match(text)
        if m:
            return m.group(3) + m.group(4) + text[m.end():]
    return text


# ---------------------------------------------------------------------------
# 8. 通用积极结论（模式 24）
# ---------------------------------------------------------------------------
# 多行模式：多段回复中每段结尾的模糊乐观结尾都会被处理。
_GENERIC_POSITIVE_RE = [
    re.compile(r"[?？]?(让我们一起|让我们一起共同)?(期待|迈向|迎接)[^。！!]{0,15}(未来|明天)[^。！!]{0,15}[。！!]?\s*$", re.M),
    re.compile(r"[?？]?(相信|愿)(未来|我们)[^。！!]{0,20}[。！!]?\s*$", re.M),
    re.compile(r"[?？]?这(是)?(一个)?(迈向|朝着)(正确|更好|光明)(方向|未来)的(重要|关键|坚实)?(一步|开始)[。！!]?\s*$", re.M),
]


def _strip_generic_positive(text: str) -> str:
    """去除模糊的乐观结尾。"""
    for pat in _GENERIC_POSITIVE_RE:
        text = pat.sub("", text)
    return text.strip()


# ---------------------------------------------------------------------------
# 9. 标点与格式规范化
# ---------------------------------------------------------------------------
_MULTI_EXCLAMATION = re.compile(r"[！!]{2,}")
_MULTI_DOTS = re.compile(r"。{2,}")
# 只折叠空格/制表符；换行单独处理，避免把多段落、Markdown 表格、代码块压成单行
_SPACES = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
# Markdown 代码块保护：折叠空白前用占位符抽出，折叠后放回，
# 否则代码缩进会被折叠、Python/缩进敏感代码的语义被破坏
_FENCE_RE = re.compile(r"```.*?```", re.S)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _protect_code(text: str) -> tuple[str, list[str]]:
    """抽出围栏代码块与行内代码，替换为占位符，返回 (保护后文本, 原文列表)。"""
    blocks: list[str] = []

    def repl(m: re.Match) -> str:
        blocks.append(m.group(0))
        return f"\x00{len(blocks) - 1}\x00"

    text = _FENCE_RE.sub(repl, text)
    text = _INLINE_CODE_RE.sub(repl, text)
    return text, blocks


def _restore_code(text: str, blocks: list[str]) -> str:
    """把占位符还原为代码原文。"""
    for i, block in enumerate(blocks):
        text = text.replace(f"\x00{i}\x00", block)
    return text


def normalize_punctuation(text: str) -> str:
    """多个感叹号收敛为单个，连续句号收敛为省略号，多余空格折叠。

    换行符不受影响：仅将 3 个及以上连续换行收敛为 2 个，保留段落结构。
    Markdown 围栏代码块与行内代码内的空白不受折叠影响。
    """
    text = _MULTI_EXCLAMATION.sub("！", text)
    text = _MULTI_DOTS.sub("……", text)
    protected, blocks = _protect_code(text)
    protected = _SPACES.sub(" ", protected)
    protected = _MULTI_NEWLINE.sub("\n\n", protected)
    return _restore_code(protected, blocks)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
# 按顺序执行的中文规则阶段，供 clean_zh 与 humanizer_core 的命中检测复用
ZH_STAGES = [
    ("courtesy", _strip_courtesy),
    ("disclaimers", _strip_disclaimers),
    ("fillers", _strip_fillers),
    ("hedging", _strip_hedging),
    ("dashes", _fix_dashes),
    ("neg_contrast", _strip_neg_contrast),
    ("generic_positive", _strip_generic_positive),
    ("punctuation", normalize_punctuation),
]


def clean_zh(text: str, remove_emoji_flag: bool = True) -> str:
    """按顺序执行全部中文规则。"""
    if remove_emoji_flag:
        text = remove_emoji(text)
    for _, fn in ZH_STAGES:
        text = fn(text)
    cleaned = text.strip()
    # 防御：整段被规则删空时返回原文，避免把 AI 回复清空
    return cleaned if cleaned else text
