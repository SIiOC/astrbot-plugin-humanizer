"""自适应等待时长计算规则测试。"""

import asyncio

import sys

import pytest

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from humanizer_core.debounce import DebounceEngine


def make_engine(**overrides):
    defaults = dict(
        debounce_time=2.0,
        enable_adaptive_debounce=True,
        adaptive_min_wait=1.0,
        adaptive_max_wait=6.0,
        adaptive_max_total_wait=12.0,
        adaptive_short_message_threshold=10,
        max_session_wait=60.0,
    )
    defaults.update(overrides)
    return DebounceEngine(**defaults)


def test_fixed_debounce_when_adaptive_disabled():
    engine = make_engine(enable_adaptive_debounce=False)
    wait, flush_now, reason = engine.calculate_wait("任意长度的消息内容" * 10)
    assert wait == 2.0
    assert flush_now is False
    assert reason == "fixed_debounce"


def test_length_bucket_boundaries():
    engine = make_engine()
    # 注意：无标点结尾会叠加 PLAIN_END_BONUS，以下期望值均已计入
    assert engine.calculate_wait("中")[0] == pytest.approx(4.8)        # 1 字 → very_short(4.0) + 0.8
    assert engine.calculate_wait("中" * 3)[0] == pytest.approx(4.8)    # 3 字 → very_short(4.0) + 0.8
    assert engine.calculate_wait("中" * 4)[0] == pytest.approx(4.0)    # 4 字 → short(3.2) + 0.8
    assert engine.calculate_wait("中" * 10)[0] == pytest.approx(4.0)   # 10 字 → short(3.2) + 0.8
    assert engine.calculate_wait("中" * 11)[0] == pytest.approx(3.4)   # 11 字 → medium(2.7) + 0.7
    assert engine.calculate_wait("中" * 30)[0] == pytest.approx(3.4)   # 30 字 → medium(2.7) + 0.7
    assert engine.calculate_wait("中" * 31)[0] == pytest.approx(2.1)   # 31 字 → long(1.8) + 0.3
    assert engine.calculate_wait("中" * 80)[0] == pytest.approx(2.1)   # 80 字 → long(1.8) + 0.3
    assert engine.calculate_wait("中" * 81)[0] == pytest.approx(1.0)   # 81 字 → very_long(1.0)，无追加


def test_unfinished_punctuation_bonus():
    engine = make_engine()
    # 未完结标点 +1.8s（注意中文逗号计入消息长度 → 落入 very_short 桶）
    assert engine.calculate_wait("你好，")[0] == pytest.approx(5.8)    # 3 字(4.0) + 1.8
    assert engine.calculate_wait("你好...")[0] == pytest.approx(5.0)   # 5 字(3.2) + 1.8
    assert engine.calculate_wait("你好：")[0] == pytest.approx(5.8)    # 3 字(4.0) + 1.8


def test_question_discount():
    engine = make_engine()
    # 问号 -0.8s：3.2 - 0.8 = 2.4
    assert engine.calculate_wait("你吃饭了吗？")[0] == pytest.approx(2.4)
    assert engine.calculate_wait("真的吗?")[0] == pytest.approx(2.4)


def test_sentence_end_discount():
    engine = make_engine()
    # 句号 -0.5s：3.2 - 0.5 = 2.7
    assert engine.calculate_wait("我吃饭了。")[0] == pytest.approx(2.7)
    assert engine.calculate_wait("太好了!")[0] == pytest.approx(2.7)


def test_plain_end_bonus():
    engine = make_engine()
    # 无标点结尾按长度追加：4 字(≤10) +0.8 → 3.2 + 0.8 = 4.0
    assert engine.calculate_wait("随便聊聊")[0] == pytest.approx(4.0)
    # 15 字(≤30) +0.7 → 2.7 + 0.7 = 3.4
    assert engine.calculate_wait("中" * 15)[0] == pytest.approx(3.4)


def test_short_streak_bonus():
    engine = make_engine()
    session = {"short_message_count": 0}
    # 第一条短消息不触发加成（无标点 → 4.0 已含 plain_end +0.8）
    wait1, _, _ = engine.calculate_wait("你好", session)
    assert wait1 == pytest.approx(4.8)
    # 第二条连续短消息 +0.3
    wait2, _, reason2 = engine.calculate_wait("在吗", session)
    assert wait2 == pytest.approx(5.1)
    assert "short_streak_2" in reason2
    # 第三条 +0.6（"想问点事"为 4 字 → very_short 桶 3.2 + plain 0.8 + streak 0.6 = 4.6）
    wait3, _, reason3 = engine.calculate_wait("想问点事", session)
    assert wait3 == pytest.approx(4.6)
    assert "short_streak_3" in reason3
    # 第四条 +0.8（封顶档）
    wait4, _, reason4 = engine.calculate_wait("你方便吗", session)
    assert wait4 == pytest.approx(4.8)
    assert "short_streak_4" in reason4


def test_short_streak_resets_on_long_message():
    engine = make_engine()
    session = {"short_message_count": 0}
    engine.calculate_wait("短消息一", session)
    engine.calculate_wait("短消息二", session)
    assert session["short_message_count"] == 2
    engine.calculate_wait("这是一条足够长的消息用来打断短句连击", session)
    assert session["short_message_count"] == 0
    # 打断后重新从短句 1 计数
    wait, _, reason = engine.calculate_wait("嗯嗯", session)
    assert session["short_message_count"] == 1
    assert "short_streak" not in reason


def test_min_max_clamping():
    engine = make_engine(adaptive_min_wait=1.0, adaptive_max_wait=6.0)
    # very_long 消息基础 1.0，不会被钳到 1.0 以下
    assert engine.calculate_wait("中" * 100)[0] >= 1.0
    # 未完结标点长消息：1.0 + 1.8 = 2.8
    assert engine.calculate_wait("中" * 100 + "，")[0] == pytest.approx(2.8)
    # 连续短句封顶也不超过 max_wait
    session = {"short_message_count": 10}
    wait, _, _ = engine.calculate_wait("嗯嗯", session)
    assert wait <= 6.0


def test_max_total_wait_hard_cap():
    engine = make_engine(adaptive_max_total_wait=2.0)

    class FakeClock:
        def __init__(self):
            self.t = 0.0

        def __call__(self):
            return self.t

    clock = FakeClock()
    engine._now = clock
    # 首条消息在 t=0，启动会话
    session = {
        "started_at": 0.0,
        "short_message_count": 0,
    }
    clock.t = 1.9  # 已过 1.9s，剩余 0.1s
    wait, flush_now, reason = engine.calculate_wait("新消息", session)
    assert flush_now is False
    assert wait == pytest.approx(0.1)
    assert "limited_by_total_wait" in reason

    clock.t = 2.1  # 超过总上限
    wait, flush_now, reason = engine.calculate_wait("再一条", session)
    assert flush_now is True
    assert wait == 0.0
    assert "max_total_wait_reached" in reason


def test_session_independent_started_at():
    """总上限按各会话独立计时（started_at 由 submit 设置）。"""
    async def scenario():
        engine = make_engine(adaptive_max_total_wait=12.0)
        result = engine.submit("u1", text="你好")
        assert result.action == "started"
        session = engine.get_session("u1")
        assert session["started_at"] > 0
        assert session["short_message_count"] == 1  # 首条短消息计数 1
        engine.shutdown()

    asyncio.run(scenario())
