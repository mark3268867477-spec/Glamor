"""
Native SolidWorks COM / VBScript Automation Engine for Glamor PC Control.

Executes fast, reliable 3D CAD actions via cscript.exe (GBK/ANSI VBScript)
directly against a running or newly launched SldWorks.Application session,
bypassing fragile screenshot-clicking on SolidWorks ribbon menus.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable, Dict, Optional, Tuple


def _is_sldworks_running() -> bool:
    if os.name != "nt":
        return False
    try:
        kwargs: Dict[str, Any] = {"capture_output": True, "text": True, "errors": "replace", "timeout": 3.0}
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        p = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/NH"], **kwargs)
        return "SLDWORKS.EXE" in (p.stdout or "").upper()
    except Exception:
        return False


_COMMON_VBS_HELPERS = r'''
Function ConnectSolidWorks(createIfMissing, waitIfBooting)
    Dim app, i, maxTries, rev, doneBoot
    Set app = Nothing
    maxTries = 1
    If waitIfBooting Then maxTries = 44
    For i = 1 To maxTries
        On Error Resume Next
        Set app = GetObject(, "SldWorks.Application")
        If Err.Number <> 0 Then
            Err.Clear
            Set app = Nothing
        End If
        If Not (app Is Nothing) Then
            rev = app.RevisionNumber()
            If Err.Number = 0 Then
                Exit For
            End If
            Err.Clear
            Set app = Nothing
        End If
        On Error GoTo 0
        If i < maxTries Then WScript.Sleep 500
    Next
    On Error GoTo 0
    If (app Is Nothing) And createIfMissing Then
        On Error Resume Next
        Set app = CreateObject("SldWorks.Application")
        If Err.Number <> 0 Then
            Err.Clear
            Set app = Nothing
        End If
        If Not (app Is Nothing) Then
            app.Visible = True
            For i = 1 To 40
                doneBoot = False
                doneBoot = app.StartupProcessCompleted
                If Err.Number <> 0 Then
                    Err.Clear
                    rev = app.RevisionNumber()
                    If Err.Number = 0 Then doneBoot = True
                End If
                If doneBoot Then Exit For
                WScript.Sleep 500
            Next
        End If
        On Error GoTo 0
    End If
    If Not (app Is Nothing) Then
        On Error Resume Next
        app.Visible = True
        On Error GoTo 0
    End If
    Set ConnectSolidWorks = app
End Function

Function SelectPlaneSafe(doc, planeKey)
    Dim enName, cnName
    enName = "Front Plane"
    cnName = ChrW(&H524D) & ChrW(&H89C6) & ChrW(&H57FA) & ChrW(&H51C6) & ChrW(&H9762)
    If planeKey = "top" Then
        enName = "Top Plane"
        cnName = ChrW(&H4E0A) & ChrW(&H89C6) & ChrW(&H57FA) & ChrW(&H51C6) & ChrW(&H9762)
    ElseIf planeKey = "right" Then
        enName = "Right Plane"
        cnName = ChrW(&H53F3) & ChrW(&H89C6) & ChrW(&H57FA) & ChrW(&H51C6) & ChrW(&H9762)
    End If
    doc.ClearSelection2 True
    SelectPlaneSafe = doc.Extension.SelectByID2(enName, "PLANE", 0, 0, 0, False, 0, Nothing, 0)
    If SelectPlaneSafe = False Then
        doc.ClearSelection2 True
        SelectPlaneSafe = doc.Extension.SelectByID2(cnName, "PLANE", 0, 0, 0, False, 0, Nothing, 0)
    End If
End Function

Function EnsureActivePart(swApp)
    Dim m
    Set m = Nothing
    Set m = swApp.ActiveDoc
    If m Is Nothing Then
        swApp.NewPart
        Set m = swApp.ActiveDoc
    End If
    Set EnsureActivePart = m
End Function
'''


def build_sw_vbs_script(action: str, args: Dict[str, Any]) -> Tuple[str, Optional[Dict[str, str]]]:
    """Build verified GBK-safe SolidWorks VBScript for a deterministic CAD action."""
    act = (action or "").strip().lower()
    sw_proc_up = _is_sldworks_running()
    wait_flag = "True" if sw_proc_up else "False"
    create_flag = "False" if sw_proc_up else "True"

    if act in ("open", "launch", "start"):
        vbs = _COMMON_VBS_HELPERS + f'''
Dim swApp, doc
Set swApp = ConnectSolidWorks({create_flag}, {wait_flag})
If swApp Is Nothing Then
    WScript.Echo "ERR:无法启动或连接 SolidWorks（若已手动打开且无法连接，请确认 SolidWorks 与 G'lamor 权限级别一致）"
    WScript.Quit 1
End If
Set doc = swApp.ActiveDoc
If doc Is Nothing Then
    WScript.Echo "OK:SolidWorks 已启动就绪 (版本 " & swApp.RevisionNumber() & ")"
Else
    WScript.Echo "OK:SolidWorks 已启动并连接 (版本 " & swApp.RevisionNumber() & ") | 当前文档: " & doc.GetTitle()
End If
'''
        return vbs, None

    if act == "get_status":
        if sw_proc_up:
            vbs = _COMMON_VBS_HELPERS + r'''
Dim swApp, doc, title, dtype
Set swApp = ConnectSolidWorks(False, False)
If swApp Is Nothing Then
    WScript.Echo "OK:SolidWorks 正在后台启动加载中，请稍候几秒再试或直接发建模指令等待就绪。"
    WScript.Quit 0
End If
Set doc = swApp.ActiveDoc
If doc Is Nothing Then
    WScript.Echo "OK:SolidWorks 已运行 (版本 " & swApp.RevisionNumber() & ")，当前无打开文档。"
Else
    title = doc.GetTitle()
    dtype = doc.GetType()
    WScript.Echo "OK:SolidWorks 已连接 (版本 " & swApp.RevisionNumber() & ") | 当前文档: " & title & " (类型=" & dtype & ")"
End If
'''
        else:
            vbs = _COMMON_VBS_HELPERS + r'''
WScript.Echo "OK:SolidWorks 当前未运行（可直接对我说新建零件或画长方体/圆柱，会自动帮你打开 SolidWorks）。"
'''
        return vbs, None

    if act == "new_part":
        vbs = _COMMON_VBS_HELPERS + f'''
Dim swApp, doc
Set swApp = ConnectSolidWorks({create_flag}, {wait_flag})
If swApp Is Nothing Then
    WScript.Echo "ERR:无法启动或连接 SolidWorks"
    WScript.Quit 1
End If
swApp.NewPart
Set doc = swApp.ActiveDoc
If doc Is Nothing Then
    WScript.Echo "ERR:新建零件失败"
    WScript.Quit 1
End If
WScript.Echo "OK:已在 SolidWorks 中新建空白零件 (" & doc.GetTitle() & ")"
'''
        return vbs, None

    if act == "create_box":
        length = float(args.get("length") or 50.0)
        width = float(args.get("width") or 30.0)
        height = float(args.get("height") or 20.0)
        hl = (length / 1000.0) / 2.0
        hw = (width / 1000.0) / 2.0
        hm = height / 1000.0
        plane = str(args.get("plane") or "front").strip().lower()
        vbs = _COMMON_VBS_HELPERS + f'''
Dim swApp, model, ok, feat
Set swApp = ConnectSolidWorks({create_flag}, {wait_flag})
If swApp Is Nothing Then
    WScript.Echo "ERR:无法连接 SolidWorks"
    WScript.Quit 1
End If
Set model = EnsureActivePart(swApp)
If model Is Nothing Then
    WScript.Echo "ERR:无法获取或新建零件文档"
    WScript.Quit 1
End If
ok = SelectPlaneSafe(model, "{plane}")
If ok = False Then
    WScript.Echo "ERR:选择基准面失败"
    WScript.Quit 1
End If
model.SketchManager.InsertSketch True
model.SketchManager.CreateCenterRectangle 0, 0, 0, {hl:.6f}, {hw:.6f}, 0
model.SketchManager.InsertSketch True
Set feat = model.FeatureManager.FeatureExtrusion2(True, False, False, 0, 0, {hm:.6f}, 0, False, False, False, False, 0, 0, False, False, False, False, True, True, True, 0, 0, False)
If feat Is Nothing Then
    WScript.Echo "ERR:拉伸长方体失败"
    WScript.Quit 1
End If
model.ForceRebuild3 False
model.ShowNamedView2 "", 7
model.ViewZoomtofit2
WScript.Echo "OK:已在 SolidWorks 创建长方体 {length:g}x{width:g}x{height:g} mm (" & model.GetTitle() & ")"
'''
        return vbs, None

    if act == "create_cylinder":
        diam = float(args.get("diameter") or 40.0)
        height = float(args.get("height") or 30.0)
        rm = (diam / 1000.0) / 2.0
        hm = height / 1000.0
        plane = str(args.get("plane") or "front").strip().lower()
        vbs = _COMMON_VBS_HELPERS + f'''
Dim swApp, model, ok, feat
Set swApp = ConnectSolidWorks({create_flag}, {wait_flag})
If swApp Is Nothing Then
    WScript.Echo "ERR:无法连接 SolidWorks"
    WScript.Quit 1
End If
Set model = EnsureActivePart(swApp)
If model Is Nothing Then
    WScript.Echo "ERR:无法获取或新建零件文档"
    WScript.Quit 1
End If
ok = SelectPlaneSafe(model, "{plane}")
If ok = False Then
    WScript.Echo "ERR:选择基准面失败"
    WScript.Quit 1
End If
model.SketchManager.InsertSketch True
model.SketchManager.CreateCircleByRadius 0, 0, 0, {rm:.6f}
model.SketchManager.InsertSketch True
Set feat = model.FeatureManager.FeatureExtrusion2(True, False, False, 0, 0, {hm:.6f}, 0, False, False, False, False, 0, 0, False, False, False, False, True, True, True, 0, 0, False)
If feat Is Nothing Then
    WScript.Echo "ERR:拉伸圆柱失败"
    WScript.Quit 1
End If
model.ForceRebuild3 False
model.ShowNamedView2 "", 7
model.ViewZoomtofit2
WScript.Echo "OK:已在 SolidWorks 创建圆柱 直径{diam:g}mm x 高{height:g}mm (" & model.GetTitle() & ")"
'''
        return vbs, None

    if act == "create_tube":
        od = float(args.get("od") or 50.0)
        idv = float(args.get("id") or 30.0)
        height = float(args.get("height") or 20.0)
        if idv >= od:
            raise ValueError(f"管件内径({idv}mm)必须小于外径({od}mm)")
        ro = (od / 1000.0) / 2.0
        ri = (idv / 1000.0) / 2.0
        hm = height / 1000.0
        plane = str(args.get("plane") or "front").strip().lower()
        vbs = _COMMON_VBS_HELPERS + f'''
Dim swApp, model, ok, feat
Set swApp = ConnectSolidWorks({create_flag}, {wait_flag})
If swApp Is Nothing Then
    WScript.Echo "ERR:无法连接 SolidWorks"
    WScript.Quit 1
End If
Set model = EnsureActivePart(swApp)
If model Is Nothing Then
    WScript.Echo "ERR:无法获取或新建零件文档"
    WScript.Quit 1
End If
ok = SelectPlaneSafe(model, "{plane}")
If ok = False Then
    WScript.Echo "ERR:选择基准面失败"
    WScript.Quit 1
End If
model.SketchManager.InsertSketch True
model.SketchManager.CreateCircleByRadius 0, 0, 0, {ro:.6f}
model.SketchManager.CreateCircleByRadius 0, 0, 0, {ri:.6f}
model.SketchManager.InsertSketch True
Set feat = model.FeatureManager.FeatureExtrusion2(True, False, False, 0, 0, {hm:.6f}, 0, False, False, False, False, 0, 0, False, False, False, False, True, True, True, 0, 0, False)
If feat Is Nothing Then
    WScript.Echo "ERR:拉伸圆环/套筒失败"
    WScript.Quit 1
End If
model.ForceRebuild3 False
model.ShowNamedView2 "", 7
model.ViewZoomtofit2
WScript.Echo "OK:已在 SolidWorks 创建圆环套筒 外径{od:g} / 内径{idv:g} / 高{height:g} mm (" & model.GetTitle() & ")"
'''
        return vbs, None

    if act in ("view", "rebuild"):
        view_name = str(args.get("view") or args.get("target") or "iso").strip().lower()
        view_ids = {"front": 1, "back": 2, "left": 3, "right": 4, "top": 5, "bottom": 6, "iso": 7, "isometric": 7}
        vid = view_ids.get(view_name, 0)
        rebuild_line = "model.ForceRebuild3 False\n" if act == "rebuild" else ""
        view_line = f'model.ShowNamedView2 "", {vid}\n' if vid > 0 else ""
        vbs = _COMMON_VBS_HELPERS + f'''
Dim swApp, model
Set swApp = ConnectSolidWorks(False, {wait_flag})
If swApp Is Nothing Then
    WScript.Echo "ERR:SolidWorks 未运行"
    WScript.Quit 1
End If
Set model = swApp.ActiveDoc
If model Is Nothing Then
    WScript.Echo "ERR:当前没有打开任何 SolidWorks 文档"
    WScript.Quit 1
End If
{rebuild_line}{view_line}model.ViewZoomtofit2
WScript.Echo "OK:已刷新 SolidWorks 视图 ({act}:{view_name})"
'''
        return vbs, None

    if act in ("save", "export"):
        raw_path = str(args.get("path") or args.get("target") or "").strip()
        if not raw_path:
            ext = "STEP" if act == "export" else "SLDPRT"
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            raw_path = os.path.join(desktop, f"solidworks_part_{time.strftime('%Y%m%d_%H%M%S')}.{ext}")
        raw_path = os.path.expandvars(os.path.expanduser(raw_path))
        _, ext = os.path.splitext(raw_path)
        if not ext:
            ext = ".STEP" if act == "export" else ".SLDPRT"
            raw_path += ext
        os.makedirs(r"C:\temp", exist_ok=True)
        tmp_out = os.path.join(r"C:\temp", f"glam_sw_export_{os.getpid()}{ext}")
        tmp_vbs_path = tmp_out.replace('"', "")
        vbs = _COMMON_VBS_HELPERS + f'''
Dim swApp, model, status, errors, warnings, fso
Set swApp = ConnectSolidWorks(False, {wait_flag})
If swApp Is Nothing Then
    WScript.Echo "ERR:SolidWorks 未运行"
    WScript.Quit 1
End If
Set model = swApp.ActiveDoc
If model Is Nothing Then
    WScript.Echo "ERR:当前没有打开任何 SolidWorks 文档"
    WScript.Quit 1
End If
errors = 0
warnings = 0
On Error Resume Next
status = model.Extension.SaveAs("{tmp_vbs_path}", 0, 2, Nothing, errors, warnings)
If Err.Number <> 0 Then
    Err.Clear
    status = model.SaveAs3("{tmp_vbs_path}", 0, 2)
End If
On Error GoTo 0
Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FileExists("{tmp_vbs_path}") Then
    WScript.Echo "ERR:保存或导出失败 (errors=" & errors & ")"
    WScript.Quit 1
End If
WScript.Echo "OK:Saved {tmp_vbs_path}"
'''
        return vbs, {"tmp_out": tmp_out, "dest_out": raw_path}

    raise ValueError(f"不支持的 SolidWorks action: {act}")


def run_vbs_text(vbs_code: str, timeout: float = 22.0) -> str:
    """Write VBScript as GBK/ANSI and execute cleanly via cscript.exe //nologo."""
    if os.name != "nt":
        raise RuntimeError("SolidWorks COM 仅支持 Windows")
    tmp_vbs = ""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".vbs", encoding="gbk", errors="replace", delete=False) as tf:
            tf.write(vbs_code)
            tmp_vbs = tf.name
        kwargs: Dict[str, Any] = {
            "capture_output": True,
            "timeout": timeout,
        }
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        proc = subprocess.run(["cscript.exe", "//nologo", tmp_vbs], **kwargs)
        out_raw = proc.stdout or b""
        err_raw = proc.stderr or b""
        out = ""
        err = ""
        for enc in ("gbk", "utf-8", "utf-8-sig"):
            try:
                out = out_raw.decode(enc).strip()
                break
            except UnicodeDecodeError:
                continue
        if not out and out_raw:
            out = out_raw.decode("gbk", errors="replace").strip()
        for enc in ("gbk", "utf-8", "utf-8-sig"):
            try:
                err = err_raw.decode(enc).strip()
                break
            except UnicodeDecodeError:
                continue
        if proc.returncode != 0 or (err and ("VBScript" in err or "错误" in err or "error" in err.lower())):
            raise RuntimeError(err or out or f"cscript exit {proc.returncode}")
        for line in reversed(out.splitlines()):
            s = line.strip()
            if s.startswith("OK:"):
                return s[3:].strip()
            if s.startswith("ERR:"):
                raise RuntimeError(s[4:].strip())
        return out or "SolidWorks VBScript 执行完成"
    finally:
        if tmp_vbs and os.path.exists(tmp_vbs):
            try:
                os.unlink(tmp_vbs)
            except OSError:
                pass


def _extract_and_clean_vbs(raw: str) -> str:
    txt = (raw or "").replace("\ufeff", "").replace("\u200b", "").replace("\u00a0", " ").replace("\r\n", "\n").strip()
    blocks = re.findall(r"```[a-zA-Z0-9_-]*\s*\n(.*?)```", txt, flags=re.DOTALL)
    if blocks:
        vbs_tokens = ("swApp", "SldWorks", "SketchManager", "FeatureManager", "Dim ", "Set ", "SelectByID2")
        scored = sorted(
            blocks,
            key=lambda b: (sum(1 for t in vbs_tokens if t in b), len(b)),
            reverse=True,
        )
        txt = scored[0].strip()
    else:
        txt = re.sub(r"^\s*```[a-zA-Z0-9_-]*\s*", "", txt)
        txt = re.sub(r"\s*```\s*$", "", txt).strip()

    txt = txt.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    lines = txt.splitlines()
    vbs_start_re = re.compile(
        r"^\s*(?:Option\s+|Const\s+|Dim\s+|On\s+Error\b|Set\s+|Function\s+|Sub\s+|For\s+|If\s+|WScript\.|swApp\.|model\.|Rem\b|')",
        flags=re.IGNORECASE,
    )
    start_idx = 0
    for i, ln in enumerate(lines):
        if vbs_start_re.match(ln):
            start_idx = i
            break
    else:
        raise ValueError(f"AI 返回内容不包含有效的 VBScript 代码开头: {txt[:120]}")

    kept = [
        ln for ln in lines[start_idx:]
        if not ln.strip().startswith("```") and not re.match(r"^\s*Option\s+Explicit\b", ln, flags=re.IGNORECASE)
    ]
    cleaned = "\n".join(kept).strip()
    if not cleaned:
        raise ValueError("AI 生成的 VBScript 内容为空")
    cleaned = re.sub(r"\bApplication\.SldWorks\b", "GlamConnectSw()", cleaned, flags=re.IGNORECASE)
    if re.search(r"^\s*(?:Sub|Function)\s+(?:AutoConnectSw|ConnectSolidWorks|SelectPlaneSafe|EnsureActivePart)\b", cleaned, flags=re.IGNORECASE | re.MULTILINE):
        cleaned = re.sub(
            r"(?is)^\s*(?:Sub|Function)\s+(?:AutoConnectSw|ConnectSolidWorks|SelectPlaneSafe|EnsureActivePart)\b.*?^\s*End\s+(?:Sub|Function)\s*$",
            "",
            cleaned,
            flags=re.MULTILINE,
        ).strip()
    if "GlamConnectSw" not in cleaned and "AutoConnectSw" not in cleaned and "ConnectSolidWorks" not in cleaned and "GetObject" not in cleaned and "CreateObject" not in cleaned:
        cleaned = (
            "Dim swApp, model\n"
            "Set swApp = GlamConnectSw()\n"
            "If swApp Is Nothing Then WScript.Quit 1\n"
            "Set model = GlamEnsurePart(swApp)\n"
            + cleaned
        )
    return cleaned


_SW_AI_SYSTEM_PROMPT = (
    "Output ONLY SolidWorks 2025 VBScript inside ```vbscript```. No Option Explicit, no prose. "
    "Call built-in globals (never redefine them, never use Application.SldWorks): "
    "Dim swApp,model,feat: Set swApp=GlamConnectSw(): If swApp Is Nothing Then WScript.Quit 1: End If: "
    "Set model=GlamEnsurePart(swApp): GlamSelectPlane model,\"front\". "
    "Units MUST be meters (mm/1000). Avoid single-line If..Then with colons for multi-statements. "
    "Boss extrude uses 23 args: model.FeatureManager.FeatureExtrusion2(True,False,False,0,0,dM,0,False,False,False,False,0,0,False,False,False,False,True,True,True,0,0,False). "
    "End with: model.ForceRebuild3 False: model.ShowNamedView2 \"\",7: model.ViewZoomtofit2: WScript.Echo \"OK:已完成建模\"."
)


def execute_solidworks_action(
    args: Dict[str, Any],
    ai_cfg: Optional[Dict[str, Any]] = None,
    log_cb: Optional[Callable[[str, str], None]] = None,
) -> str:
    act = str(args.get("action") or "get_status").strip().lower()
    if act == "ai_model":
        goal = str(args.get("goal") or args.get("target") or args.get("extra") or "").strip()
        if not goal:
            raise ValueError("缺少 SolidWorks AI 建模需求描述 goal")
        cfg = dict(ai_cfg or {})
        if not str(cfg.get("api_key") or "").strip():
            raise ValueError("使用 ai_model 需先在 G'lamor 填写 API Key；常规操作可直接用 create_box/create_cylinder/create_tube/view/save。")
        from .vision_agent import _call_chat_api

        if log_cb:
            log_cb(f"[SolidWorks AI] 生成并执行建模脚本: {goal}", "cmd")
        sw_proc_up = _is_sldworks_running()
        c_flag = "False" if sw_proc_up else "True"
        w_flag = "True" if sw_proc_up else "False"
        auto_hdr = (
            _COMMON_VBS_HELPERS
            + f"\nFunction GlamConnectSw()\n    Set GlamConnectSw = ConnectSolidWorks({c_flag}, {w_flag})\nEnd Function"
            + "\nFunction AutoConnectSw()\n    Set AutoConnectSw = GlamConnectSw()\nEnd Function"
            + "\nFunction GlamEnsurePart(swApp)\n    Set GlamEnsurePart = EnsureActivePart(swApp)\nEnd Function"
            + "\nFunction GlamSelectPlane(doc, k)\n    GlamSelectPlane = SelectPlaneSafe(doc, k)\nEnd Function\n"
        )
        raw = _call_chat_api(
            cfg,
            system_prompt=_SW_AI_SYSTEM_PROMPT,
            user_text=f"Create concise SolidWorks VBScript: {goal}",
            image_b64=None,
            max_tokens=1400,
            timeout=25.0,
            allow_reasoning_fallback=False,
        )
        user_vbs = _extract_and_clean_vbs(raw)
        vbs = auto_hdr + "\n" + user_vbs
        try:
            return run_vbs_text(vbs, timeout=35.0)
        except Exception as exc:
            err_msg = str(exc)
            if "VBScript" in err_msg or "错误" in err_msg or "cscript" in err_msg:
                if log_cb:
                    log_cb(f"[SolidWorks AI] 脚本报错，自动自愈重写一次: {err_msg[:90]}", "warn")
                repair_raw = _call_chat_api(
                    cfg,
                    system_prompt=_SW_AI_SYSTEM_PROMPT,
                    user_text=f"Fix VBScript error:\n{err_msg}\n\nCode:\n{user_vbs[:1800]}\n\nGoal: {goal}",
                    image_b64=None,
                    max_tokens=1400,
                    timeout=25.0,
                    allow_reasoning_fallback=False,
                )
                vbs2 = auto_hdr + "\n" + _extract_and_clean_vbs(repair_raw)
                return run_vbs_text(vbs2, timeout=35.0)
            raise

    vbs, move_info = build_sw_vbs_script(act, args)
    res = run_vbs_text(vbs, timeout=35.0)
    if move_info:
        src = move_info["tmp_out"]
        dst = move_info["dest_out"]
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        shutil.move(src, dst)
        return f"已导出 SolidWorks 文件: {dst}"
    return res
