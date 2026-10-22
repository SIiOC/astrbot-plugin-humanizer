# -*- coding: utf-8 -*-
"""主动消息插话丢弃判定测试（v3.2：user_interjected_during）。"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from humanizer_core.proactive import user_interjected_during


def test_no_interjection_when_no_new_message():
    """触发时刻之后没有新发言：不丢弃。"""
    assert user_interjected_during(1000.0, 999.0) is False


def test_interjection_after_start():
    """生成期间用户发言（时间戳晚于发送开始）：丢弃。"""
    assert user_interjected_during(1000.0, 1000.5) is True


def test_equal_timestamp_not_interjection():
    """恰好同刻（同一 time.time() 取值）不算插话，避免把触发前最后
    一条消息误判为插话。"""
    assert user_interjected_during(1000.0, 1000.0) is False


def test_missing_history_returns_false():
    """无最后发言时间（旧状态迁移/极端场景）：不丢弃，正常发送。"""
    assert user_interjected_during(1000.0, None) is False
    assert user_interjected_during(1000.0, 0.0) is False


def test_invalid_started_ts_returns_false():
    """started_ts 非法（0/负）时保守返回 False，不因时钟异常而停发。"""
    assert user_interjected_during(0.0, 2000.0) is False
    assert user_interjected_during(-1.0, 2000.0) is False
