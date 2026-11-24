"""
Local Computer-Use Sub-Agent for Glamor PC Control.

Runs the full screenshot/SoM + Windows UIA observation -> VLM/LLM ReAct loop
locally on Windows PC so ESP32 / XiaoZhi stays lightweight and text-only.
Supports both OpenAI-compatible (DeepSeek, OpenAI, Qwen-VL, etc.) and
Anthropic-compatible (Claude) BYOK endpoints using Python stdlib only.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple


AI_PROVIDER_PRESETS: Dict[str, Dict[str, Any]] = {
    "DeepSeek 视觉 (deepseek-flash)": {
        "api_format": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-flash",
        "use_vision": True,
    },
    "DeepSeek 纯文本 UIA (deepseek-chat)": {
        "api_format": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "use_vision": False,
    },
    "Anthropic Claude (claude-3-7-sonnet)": {
        "api_format": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-3-7-sonnet-latest",
        "use_vision": True,
    },
    "OpenAI (gpt-4o)": {
        "api_format": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "use_vision": True,
    },
    "通义千问 Qwen-VL": {
        "api_format": "openai",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-vl-max",
        "use_vision": True,
    },
    "自定义 (OpenAI / Anthropic)": {},
}

DEFAULT_AI_AGENT_CONFIG: Dict[str, Any] = {
    "preset": "DeepSeek 视觉 (deepseek-flash)",
    "api_format": "openai",
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "",
    "model": "deepseek-flash",
    "use_vision": True,
    "max_steps": 8,
}

_SYSTEM_PROMPT = (
    'Windows desktop GUI agent. Reply ONLY a single JSON object (no extra text): '
    '{"thought":"","action":"click_id|click_norm|type_id|type_text|hotkey|scroll|open_app|open_url|wait|need_confirm|done",'
    '"id":1,"x":500,"y":500,"button":"left","text":"","press_enter":false,"delta":-5,"summary":""}. '
    'Prefer click_id/type_id from UIA list; use click_norm(0..1000) for visual targets on screenshot. '
    'Use need_confirm before irreversible send/delete/payment clicks. Keep summary concise Chinese (<50 chars).'
)


class VisionApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        self.status = int(status)
        self.body = body
        super().__init__(f"HTTP {status}: {body[:240]}")


def _build_endpoint(base_url: str, api_format: str) -> str:
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        raw = "https://api.anthropic.com/v1" if api_format == "anthropic" else "https://api.deepseek.com/v1"
    parsed = urllib.parse.urlparse(raw)
    path = (parsed.path or "").rstrip("/")
    if api_format == "anthropic":
        if path.endswith("/messages"):
            return raw
        if path.endswith("/v1"):
            return raw + "/messages"
        return raw + ("/messages" if path else "/v1/messages")
    if path.endswith("/chat/completions"):
        return raw
    if path:
        return raw + "/chat/completions"
    return raw + "/v1/chat/completions"


def build_openai_payload(
    model: str,
    system_prompt: str,
    user_text: str,
    image_b64: Optional[str] = None,
    max_tokens: int = 450,
) -> Dict[str, Any]:
    if image_b64:
        user_content: Any = [
            {"type": "text", "text": user_text},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            },
        ]
    else:
        user_content = user_text
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }


def build_anthropic_payload(
    model: str,
    system_prompt: str,
    user_text: str,
    image_b64: Optional[str] = None,
    max_tokens: int = 450,
) -> Dict[str, Any]:
    blocks: List[Dict[str, Any]] = []
    if image_b64:
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_b64,
                },
            }
        )
    blocks.append({"type": "text", "text": user_text})
    return {
        "model": model,
        "system": system_prompt,
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "messages": [
            {"role": "user", "content": blocks if image_b64 else user_text},
        ],
    }


_PREFER_DIRECT = False
_DEEPSEEK_NO_THINK_OK = True


def _urlopen_smart(url: str, data: bytes, headers: Dict[str, str], timeout: float) -> bytes:
    global _PREFER_DIRECT
    import http.client

    def _mk() -> urllib.request.Request:
        return urllib.request.Request(url, data=data, headers=dict(headers), method="POST")

    direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for retry in range(2):
        try:
            if _PREFER_DIRECT:
                with direct_opener.open(_mk(), timeout=timeout) as resp:
                    return resp.read()
            try:
                with urllib.request.urlopen(_mk(), timeout=timeout) as resp:
                    return resp.read()
            except urllib.error.HTTPError:
                raise
            except (urllib.error.URLError, http.client.HTTPException, OSError):
                _PREFER_DIRECT = True
                with direct_opener.open(_mk(), timeout=timeout) as resp:
                    return resp.read()
        except urllib.error.HTTPError:
            raise
        except (http.client.HTTPException, OSError):
            if retry == 1:
                raise
            time.sleep(0.35)


def _call_chat_api(
    cfg: Dict[str, Any],
    system_prompt: str,
    user_text: str,
    image_b64: Optional[str] = None,
    max_tokens: int = 1500,
    timeout: float = 28.0,
    allow_reasoning_fallback: bool = True,
    disable_thinking: bool = True,
) -> str:
    global _DEEPSEEK_NO_THINK_OK
    api_format = str(cfg.get("api_format") or "openai").strip().lower()
    if api_format not in ("openai", "anthropic"):
        api_format = "openai"
    api_key = str(cfg.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("未填写 API Key，请在 G'lamor「4. 小智 PC 控制」中配置本地 AI 代理 API Key。")
    model = str(cfg.get("model") or "").strip()
    if not model:
        model = "claude-3-7-sonnet-latest" if api_format == "anthropic" else "deepseek-flash"
    base_url = str(cfg.get("base_url") or "")
    endpoint = _build_endpoint(base_url, api_format)

    if api_format == "anthropic":
        payload = build_anthropic_payload(model, system_prompt, user_text, image_b64=image_b64, max_tokens=max_tokens)
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Connection": "close",
            "User-Agent": "Glamor/1.0",
        }
    else:
        payload = build_openai_payload(model, system_prompt, user_text, image_b64=image_b64, max_tokens=max_tokens)
        is_ds = ("deepseek" in base_url.lower() or "deepseek" in model.lower())
        if disable_thinking and is_ds and _DEEPSEEK_NO_THINK_OK:
            payload["thinking"] = {"type": "disabled"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Connection": "close",
            "User-Agent": "Glamor/1.0",
        }

    body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        raw = _urlopen_smart(endpoint, body_bytes, headers, timeout=timeout).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = str(e)
        if e.code in (400, 422) and "thinking" in payload and "thinking" in err_body.lower():
            _DEEPSEEK_NO_THINK_OK = False
            payload.pop("thinking", None)
            retry_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            try:
                raw = _urlopen_smart(endpoint, retry_bytes, headers, timeout=timeout).decode("utf-8", errors="replace")
            except urllib.error.HTTPError as e2:
                raise VisionApiError(e2.code, err_body) from e2
        else:
            raise VisionApiError(e.code, err_body) from e

    data = json.loads(raw)
    if api_format == "anthropic":
        parts = []
        for blk in data.get("content", []) or []:
            if isinstance(blk, dict) and blk.get("type") == "text":
                parts.append(str(blk.get("text", "")))
        return "\n".join(parts).strip()

    choices = data.get("choices") or []
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") or {}
        content = msg.get("content", "")
        if isinstance(content, list):
            text_out = "\n".join(str(x.get("text", "")) for x in content if isinstance(x, dict)).strip()
        else:
            text_out = str(content or "").strip()
        if not text_out and msg.get("reasoning_content"):
            if not allow_reasoning_fallback:
                raise RuntimeError("模型推理思考耗尽长度，未输出最终代码，请简化指令或重试")
            text_out = str(msg.get("reasoning_content")).strip()
        return text_out
    raise RuntimeError(f"模型返回格式异常: {raw[:200]}")


def _is_vision_unsupported_error(exc: Exception) -> bool:
    txt = str(exc).lower()
    if isinstance(exc, VisionApiError):
        txt = (exc.body or "").lower() + " " + txt
    hints = (
        "image_url",
        "image",
        "vision",
        "multimodal",
        "unknown variant",
        "content must be a string",
        "expected a string",
        "does not support image",
    )
    return any(h in txt for h in hints)


def extract_action_json(raw_text: str) -> Dict[str, Any]:
    txt = (raw_text or "").strip()
    if not txt:
        raise ValueError("模型返回空内容")
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", txt, flags=re.DOTALL | re.IGNORECASE)
    if m:
        txt = m.group(1).strip()
    try:
        obj = json.loads(txt)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    start = txt.find("{")
    end = txt.rfind("}")
    if start >= 0 and end > start:
        obj = json.loads(txt[start : end + 1])
        if isinstance(obj, dict):
            return obj
    raise ValueError(f"无法解析模型动作 JSON: {raw_text[:180]}")


def test_ai_connection(cfg: Dict[str, Any]) -> Tuple[bool, str]:
    merged = dict(DEFAULT_AI_AGENT_CONFIG)
    merged.update(cfg or {})
    try:
        reply = _call_chat_api(
            merged,
            system_prompt="You are a connectivity probe.",
            user_text="Reply with OK only.",
            image_b64=None,
            max_tokens=256,
            timeout=15.0,
        )
        return True, f"连接成功 ({merged.get('api_format')}/{merged.get('model')}): {reply[:60]}"
    except Exception as exc:
        return False, f"连接失败: {exc}"


class LocalComputerUseAgent:
    """Runs multi-step Computer Use loop on Windows PC using UIA + optional SoM vision."""

    def __init__(
        self,
        cfg: Optional[Dict[str, Any]] = None,
        log_cb: Optional[Callable[[str, str], None]] = None,
    ):
        self.cfg = dict(DEFAULT_AI_AGENT_CONFIG)
        if isinstance(cfg, dict):
            self.cfg.update(cfg)
        self._log_cb = log_cb

    def _log(self, msg: str, tag: str = "cmd") -> None:
        if self._log_cb:
            self._log_cb(msg, tag)

    def run_task(
        self,
        goal: str,
        executor: Any,
        perm_mode: str = "partial",
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> str:
        from .pc_agent import (
            norm_to_screen_xy,
            win32_capture_som_jpeg,
            win32_inspect_and_capture_som,
            win32_inspect_ui,
            win32_send_hotkey,
            win32_type_text,
        )

        api_key = str(self.cfg.get("api_key") or "").strip()
        if not api_key:
            return "未配置本地 AI 视觉代理 API Key。请在电脑端 G'lamor「4. 小智 PC 控制」中填写 DeepSeek / OpenAI / Claude API Key。"

        max_steps = max(1, min(15, int(self.cfg.get("max_steps") or 8)))
        use_vision = bool(self.cfg.get("use_vision", True))
        executor.clear_cancel()

        history: List[str] = []
        last_action_sig = ""
        repeat_count = 0

        self._log(f"[AI代理] 开始任务(最多{max_steps}步, 视觉={'开' if use_vision else '纯UIA'}): {goal}", "cmd")

        for step in range(1, max_steps + 1):
            if executor.check_failsafe():
                return "AI 桌面任务已紧急停止（检测到手动停止或鼠标移至左上角急停区）。"
            if progress_cb:
                progress_cb(step, "采集桌面状态")

            img_b64: Optional[str] = None
            if use_vision:
                try:
                    win_info, elements, img_b64 = win32_inspect_and_capture_som(
                        max_items=30, max_width=960, quality=68
                    )
                    executor._ui_elements_cache = {int(el["id"]): el for el in elements if "id" in el}
                except Exception as exc:
                    win_info, elements = {"title": "", "process": "", "sw": 1920, "sh": 1080}, []
                    self._log(f"[AI代理] 截屏/UIA采集异常: {exc}", "warn")
            else:
                try:
                    win_info, elements = win32_inspect_ui(max_items=30)
                    executor._ui_elements_cache = {int(el["id"]): el for el in elements if "id" in el}
                except Exception as exc:
                    win_info, elements = {"title": "", "process": "", "sw": 1920, "sh": 1080}, []
                    self._log(f"[AI代理] UIA读取异常: {exc}", "warn")

            uia_lines = [
                f"[{el['id']}] {el['name']} ({el['role']}) @norm({el['nx']},{el['ny']})"
                for el in elements
            ]
            hist_txt = "\n".join(f"- {h}" for h in history[-5:]) if history else "(无)"
            user_prompt = (
                f"用户目标: {goal}\n"
                f"当前第 {step}/{max_steps} 步\n"
                f"当前活动窗口: {win_info.get('title') or '(无标题)'} ({win_info.get('process') or 'app'}), "
                f"屏幕 {win_info.get('sw', 1920)}x{win_info.get('sh', 1080)}\n"
                f"最近执行历史:\n{hist_txt}\n\n"
                f"当前窗口可交互 UIA 控件 ({len(elements)}个):\n"
                + ("\n".join(uia_lines) if uia_lines else "(未检测到标准 UIA 控件，可参考截图归一化坐标或使用快捷键/open_app)")
            )

            try:
                raw_reply = _call_chat_api(
                    self.cfg,
                    system_prompt=_SYSTEM_PROMPT,
                    user_text=user_prompt,
                    image_b64=img_b64,
                    max_tokens=400,
                    timeout=14.0 if img_b64 else 20.0,
                )
            except Exception as exc:
                if img_b64:
                    if _is_vision_unsupported_error(exc):
                        use_vision = False
                        self._log(f"[AI代理] 模型 {self.cfg.get('model')} 不支持图片输入，自动切换纯 UIA 文本闭环", "warn")
                    else:
                        self._log(f"[AI代理] 看图请求异常({type(exc).__name__})，本步改用纯 UIA 控件树快速继续", "warn")
                    try:
                        raw_reply = _call_chat_api(
                            self.cfg,
                            system_prompt=_SYSTEM_PROMPT,
                            user_text=user_prompt,
                            image_b64=None,
                            max_tokens=400,
                            timeout=18.0,
                        )
                    except Exception as exc2:
                        return f"AI 代理调用第 {step} 步纯 UIA 回退接口失败: {exc2}"
                else:
                    return f"AI 代理调用第 {step} 步接口失败: {exc}"

            try:
                cmd = extract_action_json(raw_reply)
            except Exception as exc:
                return f"AI 代理第 {step} 步解析失败: {exc}"

            act = str(cmd.get("action") or "").strip().lower()
            thought = str(cmd.get("thought") or "")[:90]
            summary = str(cmd.get("summary") or "").strip()
            self._log(f"[AI代理 #{step}] {act}: {thought}", "cmd")
            if progress_cb:
                progress_cb(step, f"{act}: {thought[:32]}")

            if act == "done":
                return summary or "已完成桌面自动化任务。"

            if act == "need_confirm":
                if perm_mode == "full":
                    history.append(f"step{step}: 模型请求确认但当前为完全权限，请直接执行或改用具体点击")
                    continue
                return f"【需要用户确认】{summary or thought}。若确认继续，请直接告诉小智确认执行。"

            sig = f"{act}:{cmd.get('id')}:{cmd.get('x')}:{cmd.get('y')}:{cmd.get('text')}"
            if sig == last_action_sig:
                repeat_count += 1
                if repeat_count >= 2:
                    return f"AI 代理检测到连续重复动作({act})无进展，已提前中止。当前窗口: {win_info.get('title', '')}"
            else:
                last_action_sig = sig
                repeat_count = 0

            if executor.check_failsafe():
                return "AI 桌面任务已紧急停止。"

            try:
                if act == "click_id":
                    res = executor._tool_click_element({"target": str(cmd.get("id", "")), "button": cmd.get("button", "left")})
                elif act == "click_norm":
                    px, py = norm_to_screen_xy(float(cmd.get("x", 500)), float(cmd.get("y", 500)))
                    res = executor._tool_input_control({"action": "mouse_click", "x": px, "y": py, "button": cmd.get("button", "left")})
                elif act == "type_id":
                    res = executor._tool_type_element({
                        "target": str(cmd.get("id", "")),
                        "text": str(cmd.get("text", "")),
                        "press_enter": bool(cmd.get("press_enter", False)),
                    })
                elif act == "type_text":
                    txt = str(cmd.get("text") or "")
                    win32_type_text(txt, press_enter=bool(cmd.get("press_enter", False)))
                    res = f"输入 {len(txt)} 字符"
                elif act == "hotkey":
                    keys = str(cmd.get("text") or "")
                    win32_send_hotkey(keys)
                    res = f"热键 {keys}"
                elif act == "scroll":
                    delta = int(cmd.get("delta", -5))
                    res = executor._tool_input_control({"action": "mouse_scroll", "scroll": delta})
                elif act == "open_app":
                    res = executor._tool_app_control({"action": "open", "target": str(cmd.get("text") or "")})
                    time.sleep(0.5)
                elif act == "open_url":
                    res = executor._tool_browser_control({"action": "open_url", "target": str(cmd.get("text") or "")})
                    time.sleep(0.6)
                elif act == "wait":
                    time.sleep(0.9)
                    res = "等待界面刷新"
                else:
                    res = f"忽略未知动作 {act}"
                history.append(f"step{step} {act} -> {res[:80]}")
            except Exception as exc:
                history.append(f"step{step} {act} 失败 -> {exc}")

            time.sleep(0.28)

        return f"已完成 {max_steps} 步桌面操作（{history[-1] if history else '已执行'}），如需继续请告诉我。"
