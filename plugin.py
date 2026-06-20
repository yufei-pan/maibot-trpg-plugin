"""麦麦跑团 / MaiTRPG 插件主体。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maibot_sdk import Command, Field, MaiBotPlugin, PluginConfigBase, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

import asyncio
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

    def _run_ready_check(self, stream_id: str, sid: str):
        meta = self._load_meta(stream_id, sid)
        return trpg_session.ready_check(meta, bible_present={}, schema={}, sheets={})

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
