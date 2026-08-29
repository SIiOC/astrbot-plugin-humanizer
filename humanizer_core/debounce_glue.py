"""
防抖事件工具层：解析、识别、静音与重构。

v3.2.0 自独立插件 astrbot_plugin_chat_debounce v0.1.0 原样并入。注意：本模块是
humanizer_core 包中唯一允许直接依赖 astrbot 运行时（消息组件/事件对象）的例外，
其余模块保持纯函数约定。

负责把 AstrBot 事件对象映射为防抖引擎需要的输入（文本/图片/指令/撤回/输入状态），
并把合并结果写回事件继续传播。

对应原版 astrbot_plugin_continuous_message 的已知问题修复：
- 文本提取改为白名单制（isinstance(Plain) 或类名 {Plain, Text}），
  避免 At 等带展示文本的组件被误吸入合并缓冲（原版 hasattr 宽松匹配问题）；
- 图片仍采用 raw_message 平台原始链优先，组件链解析作回退；
- 静音优先公开 API stop_event()/clear_result()，仅在 stop_event 抛异常时
  才写私有属性 _force_stopped 兜底（降低对框架私有实现的耦合）；
- 事件重构的组件链构建失败输出 warning 日志，不再静默降级。
"""

from typing import List, Optional, Tuple

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

try:
    from astrbot.api.message_components import Plain, Image
    PLAIN_COMPONENTS = (Plain,)
except ImportError:  # 兜底：类名识别
    Plain = None
    Image = None
    PLAIN_COMPONENTS = ()
    try:
        from astrbot.api.message import Plain as PlainV2, Image as ImageV2
        Plain = PlainV2
        Image = ImageV2
        PLAIN_COMPONENTS = (Plain,)
    except ImportError:
        logger.warning("[Humanizer·防抖] 消息组件导入失败，事件重构将退化为仅同步 message_str")


def _component_kind(component) -> Optional[str]:
    """识别组件类别：text / image / other。无法识别返回 None。"""
    if component is None:
        return None
    class_name = component.__class__.__name__
    if PLAIN_COMPONENTS and isinstance(component, PLAIN_COMPONENTS):
        return "text"
    if class_name in {"Plain", "Text"}:
        return "text"
    if Image is not None and isinstance(component, Image):
        return "image"
    if class_name == "Image":
        return "image"
    return "other"


def parse_message(message_obj) -> Tuple[str, bool, List[str]]:
    """提取文本与图片。

    返回 (text, has_image, image_urls)。文本白名单制；图片优先取平台
    raw_message 原始链里的持久 URL，组件链解析仅作回退。
    """
    text = ""
    has_image = False
    image_urls: List[str] = []

    try:
        if hasattr(message_obj, "message"):
            for component in message_obj.message:
                kind = _component_kind(component)
                if kind == "text":
                    value = getattr(component, "text", None) or getattr(component, "content", None)
                    if value:
                        text += value
                elif kind == "image":
                    has_image = True
                    url = getattr(component, "url", None) or getattr(component, "file", None)
                    if url:
                        image_urls.append(url)
    except Exception as exc:
        logger.error(f"[Humanizer·防抖] 消息解析异常: {exc}")

    raw_urls = _extract_image_urls_from_raw_message(message_obj)
    if raw_urls:
        image_urls = raw_urls
        has_image = True

    return text, has_image, _dedupe_keep_order(image_urls)


def _raw_get(raw, key, default=None):
    try:
        if isinstance(raw, dict):
            return raw.get(key, default)
        if hasattr(raw, "get"):
            return raw.get(key, default)
    except Exception:
        pass
    return getattr(raw, key, default)


def _extract_image_urls_from_raw_message(message_obj) -> List[str]:
    raw = getattr(message_obj, "raw_message", None)
    raw_chain = _raw_get(raw, "message", [])
    if not isinstance(raw_chain, list):
        return []

    image_urls: List[str] = []
    for segment in raw_chain:
        if not isinstance(segment, dict) or segment.get("type") != "image":
            continue
        data = segment.get("data") or {}
        if not isinstance(data, dict):
            continue
        image_ref = data.get("url") or data.get("file")
        if image_ref:
            image_urls.append(str(image_ref))
    return _dedupe_keep_order(image_urls)


@staticmethod
def _dedupe_keep_order(values: List[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


# AstrMessageEvent / message_obj 的类名兼容判断
def _is_aiocqhttp_message_event(event: AstrMessageEvent) -> bool:
    return event.__class__.__name__ == "AiocqhttpMessageEvent"


def is_typing_event(event: AstrMessageEvent) -> bool:
    """检测输入状态通知（NapCat input_status）。"""
    if not _is_aiocqhttp_message_event(event):
        return False
    try:
        raw = getattr(event.message_obj, "raw_message", None)
        if raw is None:
            return False
        return (
            raw.get("post_type") == "notice"
            and raw.get("sub_type") == "input_status"
        )
    except Exception:
        return False


def get_typing_status_text(event: AstrMessageEvent) -> str:
    raw = getattr(event.message_obj, "raw_message", None)
    try:
        return str(raw.get("status_text", "")) if isinstance(raw, dict) else ""
    except Exception:
        return ""


def is_typing_active(event: AstrMessageEvent) -> bool:
    """判断输入状态通知是否为"正在输入"（兼容中英文关键词）。"""
    status_text = get_typing_status_text(event).lower()
    return "正在输入" in status_text or "typing" in status_text


def is_recall_event(event: AstrMessageEvent) -> bool:
    """检测撤回通知（friend_recall / group_recall）。"""
    if not _is_aiocqhttp_message_event(event):
        return False
    try:
        raw = getattr(event.message_obj, "raw_message", None)
        if not isinstance(raw, dict):
            return False
        return (
            raw.get("post_type") == "notice"
            and raw.get("notice_type") in ("friend_recall", "group_recall")
        )
    except Exception:
        return False


def get_recalled_message_id(event: AstrMessageEvent):
    try:
        raw = getattr(event.message_obj, "raw_message", None)
        if isinstance(raw, dict):
            return raw.get("message_id")
    except Exception:
        pass
    return None


def get_message_id(event: AstrMessageEvent):
    """优先 message_obj.message_id，回退 raw_message['message_id']。"""
    try:
        mid = getattr(event.message_obj, "message_id", None)
        if mid is not None:
            return mid
        raw = getattr(event.message_obj, "raw_message", None)
        if isinstance(raw, dict):
            return raw.get("message_id")
    except Exception:
        pass
    return None


def is_command(message: str, prefixes: List[str]) -> bool:
    message = (message or "").strip()
    if not message:
        return False
    for prefix in prefixes or []:
        if prefix and message.startswith(prefix):
            return True
    return False


def is_private_message_event(event: AstrMessageEvent) -> bool:
    try:
        return bool(event.is_private_chat())
    except Exception:
        return False


def silence_event(event: AstrMessageEvent) -> None:
    """阻止单条事件继续触发 LLM（吞掉中间消息）。"""
    if event is None:
        return
    event.should_call_llm(True)
    try:
        event.clear_result()
    except Exception:
        pass
    try:
        event.stop_event()
    except Exception:
        try:
            event._force_stopped = True
        except Exception:
            pass
        try:
            event.clear_result()
        except Exception:
            pass


def _build_raw_message_segments(text: str, image_urls: List[str]) -> List[dict]:
    segments = []
    if text:
        segments.append({"type": "text", "data": {"text": text}})
    for image_ref in image_urls or []:
        if image_ref:
            data = {"file": image_ref}
            if str(image_ref).startswith(("http://", "https://")):
                data["url"] = image_ref
            segments.append({"type": "image", "data": data})
    return segments


def _build_raw_message_text(text: str, image_urls: List[str]) -> str:
    parts = [text] if text else []
    for image_ref in image_urls or []:
        if not image_ref:
            continue
        if str(image_ref).startswith(("http://", "https://")):
            parts.append(f"[CQ:image,file={image_ref},url={image_ref}]")
        else:
            parts.append(f"[CQ:image,file={image_ref}]")
    return "".join(parts)


def _sync_raw_message(event: AstrMessageEvent, text: str, image_urls: List[str]):
    message_obj = getattr(event, "message_obj", None)
    raw = getattr(message_obj, "raw_message", None)
    if raw is None:
        return
    try:
        raw["message"] = _build_raw_message_segments(text, image_urls)
        raw["raw_message"] = _build_raw_message_text(text, image_urls)
    except Exception:
        try:
            setattr(raw, "message", _build_raw_message_segments(text, image_urls))
            setattr(raw, "raw_message", _build_raw_message_text(text, image_urls))
        except Exception:
            pass


def reconstruct_event(
    event: AstrMessageEvent,
    text: str,
    image_urls: List[str],
):
    """把合并后的文本与图片写回事件，供框架继续传播给 LLM。"""
    if event is None:
        return
    event.message_str = text
    if hasattr(event, "message_obj"):
        try:
            event.message_obj.message_str = text
        except Exception:
            pass

    _sync_raw_message(event, text, image_urls)

    if Plain is None or Image is None:
        logger.warning(
            "[Humanizer·防抖] 消息组件不可用，重构降级为仅同步 message_str/raw_message"
        )
        return

    chain = []
    if text:
        chain.append(Plain(text=text))
    for image_ref in image_urls or []:
        component = _build_image_component(image_ref)
        if component is not None:
            chain.append(component)

    try:
        event.message_obj.message = chain
    except Exception as exc:
        logger.warning(f"[Humanizer·防抖] 重构消息链失败（保留 message_str 同步）: {exc}")


def _build_image_component(image_ref: str):
    if not Image or not image_ref:
        return None
    if str(image_ref).startswith(("http://", "https://")) and hasattr(Image, "fromURL"):
        try:
            return Image.fromURL(image_ref)
        except Exception:
            pass
    try:
        return Image(file=image_ref)
    except TypeError:
        try:
            return Image(url=image_ref)
        except Exception:
            return None
    except Exception:
        return None
