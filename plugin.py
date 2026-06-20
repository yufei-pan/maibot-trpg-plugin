"""麦麦跑团 / MaiTRPG 插件主体。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maibot_sdk import Command, Field, MaiBotPlugin, PluginConfigBase, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

import asyncio
import trpg_cards
import trpg_gm
import trpg_schema
import trpg_session
import trpg_storage

CURRENT_CONFIG_VERSION = "1.0.0"


class PluginSection(PluginConfigBase):
    __ui_label__ = "基础设置"

    enabled: bool = Field(default=True, description="是否启用插件")
    config_version: str = Field(default=CURRENT_CONFIG_VERSION, description="配置版本号")
    maibot_plays: bool = Field(default=True, description="开局时麦麦是否作为玩家自动加入")


DEFAULT_GM_PROMPT = (
    "你是一位资深的跑团主持人（GM）。你负责描述场景、扮演 NPC、推进剧情，"
    "依据玩家行动给出生动、公正的叙事。你只负责叙事与裁定，绝不替玩家做决定，"
    "也绝不自行编造骰值——需要检定时用掷骰协议请求掷骰。语言：简体中文。"
)


class GMSection(PluginConfigBase):
    __ui_label__ = "GM 设置"

    main_gm_prompt: str = Field(default=DEFAULT_GM_PROMPT, description="GM 主提示词（机制与人设，可改）")
    gm_model: str = Field(default="replyer", description="GM 智能体模型：任务名或具体模型名")
    temperature: float = Field(default=0.8, description="GM 叙事温度")
    max_tokens: int = Field(default=4000, description="单次 GM 生成最大 token，<=0 交由宿主")
    timeout_seconds: int = Field(default=300, description="单次 GM 生成超时（秒），<=0 交由宿主默认值")


class LoopSection(PluginConfigBase):
    __ui_label__ = "回合循环"

    inactivity_flush_seconds: int = Field(default=45, description="台面静默多少秒后自动把发言批处理交给 GM")
    ooc_marker: str = Field(default="/ooc", description="场外发言前缀（也支持 (( )) 包裹）")
    max_consecutive_auto: int = Field(default=2, description="无真人行动时允许的最大连续自动推进次数")


class ContextSection(PluginConfigBase):
    __ui_label__ = "上下文"

    char_budget: int = Field(default=120000, description="GM 上下文字符预算（bible 置顶，超出裁剪最旧回合）")


class StorageSection(PluginConfigBase):
    __ui_label__ = "存储"

    data_dir: str = Field(default="", description="数据根目录；留空＝插件目录下 data/")


class MaiTRPGConfig(PluginConfigBase):
    plugin: PluginSection = Field(default_factory=PluginSection)
    gm: GMSection = Field(default_factory=GMSection)
    loop: LoopSection = Field(default_factory=LoopSection)
    context: ContextSection = Field(default_factory=ContextSection)
    storage: StorageSection = Field(default_factory=StorageSection)


class MaiTRPGPlugin(MaiBotPlugin):
    """麦麦跑团插件主体。"""

    config_model = MaiTRPGConfig

    def __init__(self) -> None:
        super().__init__()
        self._plugin_dir = Path(__file__).resolve().parent
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self._buffers: dict[str, Any] = {}            # stream_id -> trpg_batch.BatchBuffer
        self._consecutive_auto: dict[str, int] = {}
        self._flush_locks: dict[str, asyncio.Lock] = {}

    def _data_root(self) -> Path:
        custom = (self.config.storage.data_dir or "").strip()
        return Path(custom).expanduser() if custom else self._plugin_dir / "data"

    def _paths(self, stream_id: str, session_id: str) -> "trpg_storage.Paths":
        return trpg_storage.Paths(self._data_root(), stream_id, session_id)

    # ------------------------------------------------------------------ #
    # 会话辅助方法
    # ------------------------------------------------------------------ #
    @staticmethod
    def _resolve_stream_id(kwargs: dict[str, Any]) -> str:
        for key in ("stream_id", "session_stream", "chat_id"):
            val = kwargs.get(key)
            if val:
                return str(val)
        return ""

    def _maibot_member(self) -> str | None:
        return "麦麦" if self.config.plugin.maibot_plays else None

    def _load_meta(self, stream_id: str, sid: str) -> dict[str, Any]:
        return trpg_storage.read_toml(self._paths(stream_id, sid).session_toml)

    def _save_meta(self, stream_id: str, sid: str, meta: dict[str, Any]) -> None:
        trpg_storage.write_toml(self._paths(stream_id, sid).session_toml, meta)

    def _active_session_id(self, stream_id: str, prefer: str | None = None) -> str | None:
        sessions = trpg_storage.list_sessions(self._data_root(), stream_id)
        if prefer:
            return prefer if any(s["session_id"] == prefer for s in sessions) else None
        for status in (trpg_session.RUNNING, trpg_session.READY, trpg_session.SETUP):
            for s in sessions:
                if s["status"] == status:
                    return s["session_id"]
        return sessions[-1]["session_id"] if sessions else None

    def _bible_present(self, stream_id: str, sid: str) -> dict[str, bool]:
        p = self._paths(stream_id, sid)
        present = {}
        for key, fname in (("world", "world.md"), ("plot", "plot.md"), ("gm_subprompt", "gm_subprompt.md")):
            f = p.bible_file(fname)
            present[key] = f.exists() and bool(f.read_text(encoding="utf-8").strip())
        return present

    def _load_schema(self, stream_id: str, sid: str) -> dict[str, Any]:
        data = trpg_storage.read_toml(self._paths(stream_id, sid).bible_file("stat_schema.toml"))
        return trpg_schema.resolve_schema(data or None)

    def _load_sheets(self, stream_id: str, sid: str) -> dict[str, dict]:
        p = self._paths(stream_id, sid)
        out: dict[str, dict] = {}
        if p.characters_dir.exists():
            for child in p.characters_dir.glob("*.toml"):
                out[child.stem] = trpg_storage.read_toml(child)
        return out

    def _run_ready_check(self, stream_id: str, sid: str):
        meta = self._load_meta(stream_id, sid)
        return trpg_session.ready_check(
            meta,
            bible_present=self._bible_present(stream_id, sid),
            schema=self._load_schema(stream_id, sid),
            sheets=self._load_sheets(stream_id, sid),
        )

    def _write_bible(self, stream_id: str, key_fname: str, text: str, *, append: bool) -> None:
        sid = self._active_session_id(stream_id)
        f = self._paths(stream_id, sid).bible_file(key_fname)
        f.parent.mkdir(parents=True, exist_ok=True)
        if append and f.exists():
            text = f.read_text(encoding="utf-8").rstrip() + "\n\n" + text
        f.write_text(text.strip() + "\n", encoding="utf-8")

    async def _render_card(self, stream_id, sid, member, sheet, schema) -> str:
        template = (self._plugin_dir / "assets" / "card.html").read_text(encoding="utf-8")
        mug_path = self._paths(stream_id, sid).characters_dir / f"{trpg_storage.safe_component(member)}.mugshot"
        mug = mug_path.read_text(encoding="utf-8") if mug_path.exists() else ""
        html = trpg_cards.build_card_html(template, sheet=sheet, schema=schema, mugshot_uri=mug)
        rendered = await self.ctx.render.html2png(html, viewport={"width": 520, "height": 1, "device_scale_factor": 1})
        png_b64 = rendered.get("image_base64", "") if isinstance(rendered, dict) else str(rendered or "")
        if not png_b64:
            return ""
        return trpg_cards.to_compact_webp(png_b64, self.ctx.logger)

    # ------------------------------------------------------------------ #
    # 会话工具（@Tool）
    # ------------------------------------------------------------------ #
    @Tool("session_create",
          brief_description="【麦麦跑团/MaiTRPG·会话】在本聊天新建一场跑团会话（初始 setup，需补全 bible 与角色卡后才能开始）。",
          parameters=[ToolParameterInfo(name="title", param_type=ToolParamType.STRING, required=True, description="会话标题")])
    async def session_create(self, title: str = "", **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        title = str(title or "").strip()
        if not stream_id:
            return {"success": False, "content": "无法确定当前聊天流。"}
        if not title:
            return {"success": False, "content": "会话标题不能为空。"}
        sid = trpg_storage.safe_component(title) or "session"
        if self._load_meta(stream_id, sid):
            return {"success": False, "content": f"已存在同名会话：{sid}"}
        meta = trpg_session.new_session_meta(sid, title, maibot_member=self._maibot_member())
        self._save_meta(stream_id, sid, meta)
        return {"success": True, "content": f"已创建会话《{title}》[{sid}]，状态 setup。请补全世界/剧情/GM子提示词并让玩家加入。"}

    @Tool("session_list",
          brief_description="【麦麦跑团/MaiTRPG·会话】列出本聊天的所有会话及状态（含已停止、可重启的会话）。",
          parameters=[])
    async def session_list(self, **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        sessions = trpg_storage.list_sessions(self._data_root(), stream_id)
        if not sessions:
            return {"success": True, "content": "本聊天还没有任何跑团会话。"}
        lines = [f"·《{s['title']}》[{s['session_id']}] 状态={s['status']} 成员={len(s['members'])}" for s in sessions]
        return {"success": True, "content": "本聊天的跑团会话：\n" + "\n".join(lines)}

    @Tool("session_start",
          brief_description="【麦麦跑团/MaiTRPG·会话】开始/重启一场会话——会先跑就绪门禁，未通过则报告缺什么。",
          parameters=[ToolParameterInfo(name="session", param_type=ToolParamType.STRING, required=False, default="", description="会话ID，省略＝当前会话")])
    async def session_start(self, session: str = "", **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id, str(session).strip() or None)
        if not sid:
            return {"success": False, "content": "找不到会话，请先 session_create。"}
        report = self._run_ready_check(stream_id, sid)
        if not report.ok:
            return {"success": False, "content": "未通过就绪检查：\n- " + "\n- ".join(report.missing)}
        meta = self._load_meta(stream_id, sid)
        meta["status"] = trpg_session.RUNNING
        self._save_meta(stream_id, sid, meta)
        return {"success": True, "content": f"会话《{meta['title']}》已开始！台面就绪，开始你们的冒险吧。"}

    @Tool("session_stop",
          brief_description="【麦麦跑团/MaiTRPG·会话】停止当前会话（可日后 session_start 重启，会再次跑门禁）。",
          parameters=[ToolParameterInfo(name="session", param_type=ToolParamType.STRING, required=False, default="", description="会话ID，省略＝当前会话")])
    async def session_stop(self, session: str = "", **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id, str(session).strip() or None)
        if not sid:
            return {"success": False, "content": "找不到会话。"}
        meta = self._load_meta(stream_id, sid)
        meta["status"] = trpg_session.STOPPED
        self._save_meta(stream_id, sid, meta)
        return {"success": True, "content": f"会话《{meta['title']}》已停止。"}

    # ------------------------------------------------------------------ #
    # 设定工具（@Tool）—— bible_*
    # ------------------------------------------------------------------ #
    @Tool("bible_world",
          brief_description="【麦麦跑团/MaiTRPG·设定】写入/追加世界设定到 bible（可多次累积）。",
          parameters=[ToolParameterInfo(name="text", param_type=ToolParamType.STRING, required=True, description="世界设定文本"),
                      ToolParameterInfo(name="append", param_type=ToolParamType.BOOLEAN, required=False, default=True, description="是否追加（默认追加）")])
    async def bible_world(self, text: str = "", append: bool = True, **kwargs: Any) -> dict[str, Any]:
        return await self._bible_tool(kwargs, "world.md", text, append, "世界设定")

    @Tool("bible_plot",
          brief_description="【麦麦跑团/MaiTRPG·设定】写入/追加剧情与钩子到 bible。",
          parameters=[ToolParameterInfo(name="text", param_type=ToolParamType.STRING, required=True, description="剧情/钩子文本"),
                      ToolParameterInfo(name="append", param_type=ToolParamType.BOOLEAN, required=False, default=True, description="是否追加")])
    async def bible_plot(self, text: str = "", append: bool = True, **kwargs: Any) -> dict[str, Any]:
        return await self._bible_tool(kwargs, "plot.md", text, append, "剧情")

    @Tool("bible_gm",
          brief_description="【麦麦跑团/MaiTRPG·设定】写入本场 GM 子提示词（基调/主题/特殊裁定；就绪门禁项）。",
          parameters=[ToolParameterInfo(name="text", param_type=ToolParamType.STRING, required=True, description="GM 子提示词文本"),
                      ToolParameterInfo(name="append", param_type=ToolParamType.BOOLEAN, required=False, default=False, description="是否追加（默认覆盖）")])
    async def bible_gm(self, text: str = "", append: bool = False, **kwargs: Any) -> dict[str, Any]:
        return await self._bible_tool(kwargs, "gm_subprompt.md", text, append, "GM 子提示词")

    async def _bible_tool(self, kwargs, fname, text, append, label) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        text = str(text or "").strip()
        if not self._active_session_id(stream_id):
            return {"success": False, "content": "没有可写入的会话，请先 session_create。"}
        if not text:
            return {"success": False, "content": f"{label}内容不能为空。"}
        self._write_bible(stream_id, fname, text, append=append)
        return {"success": True, "content": f"已写入{label}。"}

    @Tool("bible_check",
          brief_description="【麦麦跑团/MaiTRPG·设定】检查就绪门禁是否通过（世界/剧情/GM子提示词/属性schema/全员角色卡）。",
          parameters=[])
    async def bible_check(self, **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id)
        if not sid:
            return {"success": False, "content": "没有会话。"}
        report = self._run_ready_check(stream_id, sid)
        if report.ok:
            return {"success": True, "content": "就绪门禁已通过，可以 session_start 开始。"}
        return {"success": True, "content": "尚未就绪，仍缺：\n- " + "\n- ".join(report.missing)}

    # ------------------------------------------------------------------ #
    # 角色卡工具（@Tool）—— sheet_*
    # ------------------------------------------------------------------ #
    @Tool("sheet_schema",
          brief_description="【麦麦跑团/MaiTRPG·角色卡】查看或设置属性 schema（mode: view/default/custom/edit）。",
          parameters=[ToolParameterInfo(name="mode", param_type=ToolParamType.STRING, required=False, default="view", description="view/default/custom/edit", enum_values=["view", "default", "custom", "edit"]),
                      ToolParameterInfo(name="data", param_type=ToolParamType.STRING, required=False, default="", description="custom: 完整 fields JSON；edit: {add,modify,remove} JSON")])
    async def sheet_schema(self, mode: str = "view", data: str = "", **kwargs: Any) -> dict[str, Any]:
        import json
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id)
        if not sid:
            return {"success": False, "content": "没有会话。"}
        path = self._paths(stream_id, sid).bible_file("stat_schema.toml")
        cur = self._load_schema(stream_id, sid)
        mode = str(mode or "view").strip().lower()
        if mode == "view":
            return {"success": True, "content": "当前字段：" + trpg_gm.schema_summary(cur)}
        if mode == "default":
            trpg_storage.write_toml(path, trpg_schema.resolve_schema(None))
            return {"success": True, "content": "已重置为默认 schema。"}
        if mode == "custom":
            parsed = json.loads(data) if data.strip() else {}
            trpg_storage.write_toml(path, trpg_schema.resolve_schema(parsed))
            return {"success": True, "content": "已设置自定义 schema。"}
        if mode == "edit":
            spec = json.loads(data) if data.strip() else {}
            new = trpg_schema.apply_edits(cur, add=spec.get("add", []), modify=spec.get("modify", []), remove=spec.get("remove", []))
            trpg_storage.write_toml(path, new)
            return {"success": True, "content": "已更新 schema：" + trpg_gm.schema_summary(new)}
        return {"success": False, "content": "未知 mode。"}

    @Tool("sheet_edit",
          brief_description="【麦麦跑团/MaiTRPG·角色卡】设置某玩家角色卡字段（按 schema 校验类型）。",
          parameters=[ToolParameterInfo(name="fields", param_type=ToolParamType.OBJECT, required=True, description="字段键值对，如 {name:..,hp:..}"),
                      ToolParameterInfo(name="member", param_type=ToolParamType.STRING, required=False, default="", description="玩家ID，省略＝当前发言者")])
    async def sheet_edit(self, fields: Any = None, member: str = "", **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id)
        member = str(member or kwargs.get("user_id") or "").strip()
        if not sid or not member:
            return {"success": False, "content": "缺少会话或玩家身份。"}
        if not isinstance(fields, dict) or not fields:
            return {"success": False, "content": "fields 不能为空。"}
        schema = self._load_schema(stream_id, sid)
        path = self._paths(stream_id, sid).character_toml(member)
        sheet = trpg_storage.read_toml(path) or trpg_schema.blank_sheet(schema)
        sheet.update(fields)
        problems = trpg_schema.validate_sheet(sheet, schema)
        trpg_storage.write_toml(path, sheet)
        if trpg_schema.sheet_complete(sheet, schema):
            meta = trpg_session.mark_card_done(self._load_meta(stream_id, sid), member)
            self._save_meta(stream_id, sid, meta)
            return {"success": True, "content": f"{member} 的角色卡已完成。"}
        return {"success": True, "content": f"已更新，但角色卡仍未完成：{('；'.join(problems)) or '继续补全'}"}

    @Tool("sheet_render",
          brief_description="【麦麦跑团/MaiTRPG·角色卡】渲染某玩家角色卡为图片并发到聊天。",
          parameters=[ToolParameterInfo(name="member", param_type=ToolParamType.STRING, required=False, default="", description="玩家ID，省略＝当前发言者")])
    async def sheet_render(self, member: str = "", **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id)
        member = str(member or kwargs.get("user_id") or "").strip()
        if not sid or not member:
            return {"success": False, "content": "缺少会话或玩家身份。"}
        schema = self._load_schema(stream_id, sid)
        sheet = trpg_storage.read_toml(self._paths(stream_id, sid).character_toml(member))
        if not sheet:
            return {"success": False, "content": f"{member} 还没有角色卡。"}
        img_b64 = await self._render_card(stream_id, sid, member, sheet, schema)
        if not img_b64:
            return {"success": False, "content": "渲染失败。"}
        await self.ctx.send.image(img_b64, stream_id)
        return {"success": True, "content": f"已发送 {member} 的角色卡。"}

    @Tool("sheet_mugshot",
          brief_description="【麦麦跑团/MaiTRPG·角色卡】把图片（data URI/base64）设为某玩家角色卡头像。",
          parameters=[ToolParameterInfo(name="image", param_type=ToolParamType.STRING, required=True, description="图片 data URI 或 base64"),
                      ToolParameterInfo(name="member", param_type=ToolParamType.STRING, required=False, default="", description="玩家ID，省略＝当前发言者")])
    async def sheet_mugshot(self, image: str = "", member: str = "", **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id)
        member = str(member or kwargs.get("user_id") or "").strip()
        image = str(image or "").strip()
        if not sid or not member:
            return {"success": False, "content": "缺少会话或玩家身份。"}
        if not image:
            return {"success": False, "content": "未提供图片。"}
        uri = image if image.startswith("data:") else f"data:image/png;base64,{image}"
        self._paths(stream_id, sid).character_toml(member).parent.mkdir(parents=True, exist_ok=True)
        (self._paths(stream_id, sid).characters_dir / f"{trpg_storage.safe_component(member)}.mugshot").write_text(uri, encoding="utf-8")
        return {"success": True, "content": f"已设置 {member} 的头像。"}

    # ------------------------------------------------------------------ #
    # 命令（面向人类用户的便捷管理）
    # ------------------------------------------------------------------ #
    @Command("trpg_session_command", description="跑团会话管理", pattern=r"^/session\s+(create|list|start|stop)(?:\s+(.*))?$")
    async def cmd_session(self, **kwargs: Any) -> Any:
        stream_id = self._resolve_stream_id(kwargs)
        groups = kwargs.get("matched_groups") or kwargs.get("groups") or ()
        action = groups[0] if groups else ""
        arg = (groups[1] if len(groups) > 1 else "") or ""
        if action == "create":
            res = await self.session_create(title=arg, stream_id=stream_id)
        elif action == "list":
            res = await self.session_list(stream_id=stream_id)
        elif action == "start":
            res = await self.session_start(session=arg, stream_id=stream_id)
        else:
            res = await self.session_stop(session=arg, stream_id=stream_id)
        await self.ctx.send.text(res["content"], stream_id)
        return None

    @Command("trpg_join_command", description="加入当前跑团会话", pattern=r"^/join\s*$")
    async def cmd_join(self, **kwargs: Any) -> Any:
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id)
        if not sid:
            await self.ctx.send.text("本聊天还没有跑团会话，先让麦麦或管理员 /session create。", stream_id)
            return None
        member = str(kwargs.get("user_id") or kwargs.get("sender_id") or "").strip()
        if not member:
            await self.ctx.send.text("无法识别你的身份，加入失败。", stream_id)
            return None
        meta = trpg_session.add_member(self._load_meta(stream_id, sid), member)
        self._save_meta(stream_id, sid, meta)
        await self.ctx.send.text(f"{member} 已加入会话，请用 /sheet 完成你的角色卡后才能开始/继续。", stream_id)
        return None

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    async def on_load(self) -> None:
        self.ctx.logger.info("麦麦跑团插件已加载")

    async def on_unload(self) -> None:
        self.ctx.logger.info("麦麦跑团插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        if scope == "self":
            self.ctx.logger.info("麦麦跑团配置已更新: version=%s", version)


def create_plugin() -> MaiTRPGPlugin:
    return MaiTRPGPlugin()
