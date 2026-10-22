# -*- coding: utf-8 -*-
"""主动消息会话白名单归一化测试（v3.2：normalize_allowlist）。"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from humanizer_core.proactive import normalize_allowlist


def test_empty_returns_empty_set():
    """空输入 = 不启用白名单（所有会话生效，兼容旧行为）。"""
    assert normalize_allowlist("") == set()
    assert normalize_allowlist(None) == set()
    assert normalize_allowlist([]) == set()


def test_single_umo():
    assert normalize_allowlist("qq_napcat:FriendMessage:123") == {
        "qq_napcat:FriendMessage:123"
    }


def test_string_separators():
    """换行/英文逗号/分号/中文逗号/中文分号都是合法分隔符。"""
    out = normalize_allowlist(
        "a:FriendMessage:1\nb:FriendMessage:2,c:FriendMessage:3；"
        "d:FriendMessage:4，e:FriendMessage:5"
    )
    assert out == {
        "a:FriendMessage:1",
        "b:FriendMessage:2",
        "c:FriendMessage:3",
        "d:FriendMessage:4",
        "e:FriendMessage:5",
    }


def test_list_with_embedded_separators():
    """列表项内部也允许分隔符（官方配置弹窗 list 场景的兜底）。"""
    out = normalize_allowlist(
        ["a:FriendMessage:1", "b:FriendMessage:2\nc:FriendMessage:3"]
    )
    assert out == {"a:FriendMessage:1", "b:FriendMessage:2", "c:FriendMessage:3"}


def test_strip_blank_and_dedupe():
    out = normalize_allowlist(" a:FriendMessage:1 , \n a:FriendMessage:1 ;;  ")
    assert out == {"a:FriendMessage:1"}


def test_non_string_items():
    assert normalize_allowlist([123, None]) == {"123"}


def test_garbage_type_via_str():
    """极端类型（数字等）经 str() 兜底，不抛异常。"""
    assert normalize_allowlist(42) == {"42"}
