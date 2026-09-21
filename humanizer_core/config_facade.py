# -*- coding: utf-8 -*-
"""配置访问门面。

本模块只负责对分组配置做统一的读取、写入和类型转换，不执行任何配置迁移，
也不依赖 AstrBot。分组别名写入时落到当前 schema 的正式分组，读取时则始终
直接反映底层配置对象的最新内容。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable


_MISSING = object()


class TypedConfig:
    """为分组配置提供带类型转换和兼容别名的访问门面。

    ``config`` 只被保存引用，不会复制或迁移。通过 :meth:`set` 或返回的
    :meth:`group` 对象所做的修改会直接反映到底层配置中；读取不存在的分组
    不会创建它，只有显式写入时才会创建目标分组。
    """

    # 当前 schema 的正式分组，以及旧配置访问辅助方法使用的语义别名。
    _GROUP_ALIASES = {
        "style": "style",
        "config": "style",
        "humanize": "humanize",
        "proactive": "proactive",
        "time": "time",
        "life": "time",
        "emotion": "emotion",
        "commitments": "proactive",
        "debounce": "typing",
        "send_discipline": "typing",
        "typing": "typing",
        "parrot": "parrot",
    }

    # 键名映射按调用方别名分组保存；直接访问正式分组时不额外改名。
    _KEY_ALIASES = {
        "life": {"extract_model": "life_extract_model"},
        "commitments": {
            "enable": "commitments_enable",
            "track_groups": "commitments_track_groups",
            "extract_model": "commitments_extract_model",
            "extract_timeout": "commitments_extract_timeout",
            "debug": "commitments_debug",
        },
        "debounce": {"enable": "debounce_enable"},
        "send_discipline": {
            "enabled": "send_discipline_enabled",
            "debug": "send_discipline_debug",
        },
    }

    def __init__(self, config: Any):
        """包装配置对象，保留其原始引用，不执行迁移或复制。"""
        self._config = config

    @property
    def raw(self) -> Any:
        """返回底层配置对象，便于需要时进行原生访问。"""
        return self._config

    @property
    def mapping(self) -> Any:
        """返回底层配置对象的别名，确保其可变性对调用方可见。"""
        return self._config

    @classmethod
    def _resolve(cls, group: str, key: str) -> tuple[str, str]:
        """把语义分组和键名解析为 schema 中实际使用的名称。"""
        target_group = cls._GROUP_ALIASES.get(group, group)
        target_key = cls._KEY_ALIASES.get(group, {}).get(key, key)
        return target_group, target_key

    @staticmethod
    def _mapping_get(mapping: Any, key: str, default: Any) -> Any:
        """从常规或轻量 mapping-like 对象读取键值。"""
        getter = getattr(mapping, "get", None)
        if getter is not None:
            try:
                return getter(key, default)
            except TypeError:
                # 兼容只接受一个参数的轻量 get 实现。
                try:
                    return getter(key)
                except (KeyError, TypeError):
                    return default
        try:
            return mapping[key]
        except (KeyError, TypeError, IndexError):
            return default

    @staticmethod
    def _is_mapping_like(value: Any) -> bool:
        """判断值是否足以作为配置分组使用。"""
        return isinstance(value, Mapping) or (
            hasattr(value, "get") and hasattr(value, "__getitem__")
        )

    def group(self, name: str) -> Any:
        """返回指定分组的底层对象；分组不存在或不是 mapping 时返回 ``None``。

        读取路径不会通过 ``setdefault`` 或其他方式创建分组。别名分组返回
        正式分组的同一个对象，因此对返回值的原地修改也会修改原配置。
        """
        target_group, _ = self._resolve(name, "")
        value = self._mapping_get(self._config, target_group, _MISSING)
        if value is _MISSING or not self._is_mapping_like(value):
            return None
        return value

    def get(self, group: str, key: str, default: Any = None) -> Any:
        """读取分组键值；缺失分组、缺失键或非 mapping 分组返回默认值。"""
        target_group, target_key = self._resolve(group, key)
        config_group = self.group(target_group)
        if config_group is None:
            return default
        return self._mapping_get(config_group, target_key, default)

    def _get_cast(
        self,
        group: str,
        key: str,
        default: Any,
        cast: Callable[[Any], Any],
    ) -> Any:
        """按当前配置辅助函数的规则完成安全数值转换。"""
        value = self.get(group, key, None)
        if value is None:
            return default
        try:
            return cast(value)
        except (TypeError, ValueError, OverflowError):
            return default

    def get_int(self, group: str, key: str, default: Any = None) -> Any:
        """读取整型配置；缺失、``None`` 或无法转换时返回默认值。"""
        return self._get_cast(group, key, default, int)

    def get_float(self, group: str, key: str, default: Any = None) -> Any:
        """读取浮点配置；缺失、``None`` 或无法转换时返回默认值。"""
        return self._get_cast(group, key, default, float)

    def set(self, group: str, key: str, value: Any) -> None:
        """写入配置并保留底层对象的可变性。

        别名分组会写入正式分组和正式键名。目标分组仅在这次显式写入时创建；
        若已有同名非 mapping 值，则按底层配置结构错误处理而不静默覆盖。
        """
        target_group, target_key = self._resolve(group, key)
        config_group = self.group(target_group)
        if config_group is None:
            existing = self._mapping_get(self._config, target_group, _MISSING)
            if existing is not _MISSING and existing is not None:
                raise TypeError(f"配置分组 {target_group!r} 不是 mapping")
            config_group = {}
            self._config[target_group] = config_group
        try:
            config_group[target_key] = value
        except TypeError as exc:
            raise TypeError(f"配置分组 {target_group!r} 不可写") from exc

    # ------------------------------------------------------------------
    # 分组访问别名：对应 main.py 中现有的配置辅助方法。
    # ------------------------------------------------------------------
    def style(self, key: str, default: Any = None) -> Any:
        """读取「表达 · 说话风格与语料」分组。"""
        return self.get("style", key, default)

    def config(self, key: str, default: Any = None) -> Any:
        """读取 ``_cfg`` 使用的 style 分组别名。"""
        return self.get("config", key, default)

    def humanize(self, key: str, default: Any = None) -> Any:
        """读取「表达 · 润色去痕」分组。"""
        return self.get("humanize", key, default)

    def proactive(self, key: str, default: Any = None) -> Any:
        """读取「主动 · 聊天与承诺簿」分组。"""
        return self.get("proactive", key, default)

    def time(self, key: str, default: Any = None) -> Any:
        """读取「感知 · 时间与节奏」分组。"""
        return self.get("time", key, default)

    def life(self, key: str, default: Any = None) -> Any:
        """读取生活状态别名；``extract_model`` 映射到 time 的正式键名。"""
        return self.get("life", key, default)

    def emotion(self, key: str, default: Any = None) -> Any:
        """读取「感知 · 情绪惯性」分组。"""
        return self.get("emotion", key, default)

    def commitments(self, key: str, default: Any = None) -> Any:
        """读取承诺簿别名，并映射到 proactive 的承诺键。"""
        return self.get("commitments", key, default)

    def debounce(self, key: str, default: Any = None) -> Any:
        """读取防抖别名，并映射到 typing 的防抖键。"""
        return self.get("debounce", key, default)

    def send_discipline(self, key: str, default: Any = None) -> Any:
        """读取发送纪律别名，并映射到 typing 的发送纪律键。"""
        return self.get("send_discipline", key, default)

    def typing(self, key: str, default: Any = None) -> Any:
        """读取「发送 · 延迟分段与防护」分组。"""
        return self.get("typing", key, default)

    # main.py 中已有的私有辅助名保留为无 AstrBot 的兼容入口。
    def _group(self, name: str, key: str, default: Any = None) -> Any:
        """兼容 main.py 的通用分组读取辅助方法。"""
        return self.get(name, key, default)

    def _group_num(
        self,
        name: str,
        key: str,
        default: Any,
        cast: Callable[[Any], Any] = float,
    ) -> Any:
        """兼容 main.py 的通用数值读取辅助方法。"""
        return self._get_cast(name, key, default, cast)

    def _h(self, key: str, default: Any = None) -> Any:
        """兼容润色分组读取。"""
        return self.humanize(key, default)

    def _p(self, key: str, default: Any = None) -> Any:
        """兼容主动聊天分组读取。"""
        return self.proactive(key, default)

    def _set_h(self, key: str, value: Any) -> None:
        """兼容润色分组写入。"""
        self.set("humanize", key, value)

    def _p_int(self, key: str, default: int) -> int:
        """兼容主动聊天整型配置读取。"""
        return self.get_int("proactive", key, default)

    def _p_f(self, key: str, default: float) -> float:
        """兼容主动聊天浮点配置读取。"""
        return self.get_float("proactive", key, default)

    def _d(self, key: str, default: Any = None) -> Any:
        """兼容防抖分组读取。"""
        return self.debounce(key, default)

    def _d_num(
        self,
        key: str,
        default: Any,
        cast: Callable[[Any], Any] = float,
    ) -> Any:
        """兼容防抖数值配置读取。"""
        return self._group_num("debounce", key, default, cast)

    def _life(self, key: str, default: Any = None) -> Any:
        """兼容生活状态分组读取。"""
        return self.life(key, default)

    def _time(self, key: str, default: Any = None) -> Any:
        """兼容时间流动分组读取。"""
        return self.time(key, default)

    def _time_f(self, key: str, default: Any, cast: Callable[[Any], Any] = float) -> Any:
        """兼容时间流动浮点配置读取。"""
        return self._group_num("time", key, default, cast)

    def _emo(self, key: str, default: Any = None) -> Any:
        """兼容情绪惯性分组读取。"""
        return self.emotion(key, default)

    def _emo_f(self, key: str, default: Any, cast: Callable[[Any], Any] = float) -> Any:
        """兼容情绪惯性浮点配置读取。"""
        return self._group_num("emotion", key, default, cast)

    def _cm(self, key: str, default: Any = None) -> Any:
        """兼容承诺簿分组读取。"""
        return self.commitments(key, default)

    def _cm_f(self, key: str, default: Any, cast: Callable[[Any], Any] = float) -> Any:
        """兼容承诺簿数值配置读取。"""
        return self._group_num("commitments", key, default, cast)

    def _rh(self, key: str, default: Any = None) -> Any:
        """兼容真人感规则的 style 分组读取。"""
        return self.style(key, default)

    def _discipline(self, key: str, default: Any = None) -> Any:
        """兼容发送纪律分组读取。"""
        return self.send_discipline(key, default)

    def _cfg(self, key: str, default: Any = None) -> Any:
        """兼容 style/config 分组读取。"""
        return self.config(key, default)

    def _set_cfg(self, key: str, value: Any) -> None:
        """兼容 style/config 分组写入。"""
        self.set("config", key, value)

    def _t(self, key: str, default: Any = None) -> Any:
        """兼容拟人打字分组读取。"""
        return self.typing(key, default)

    def _t_num(
        self,
        key: str,
        default: Any,
        cast: Callable[[Any], Any] = float,
    ) -> Any:
        """兼容拟人打字数值配置读取。"""
        return self._group_num("typing", key, default, cast)


__all__ = ["TypedConfig"]
