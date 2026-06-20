"""麦麦跑团 / MaiTRPG 插件主体。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maibot_sdk import Field, MaiBotPlugin, PluginConfigBase

import asyncio
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

    async def on_load(self) -> None:
        self.ctx.logger.info("麦麦跑团插件已加载")

    async def on_unload(self) -> None:
        self.ctx.logger.info("麦麦跑团插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        if scope == "self":
            self.ctx.logger.info("麦麦跑团配置已更新: version=%s", version)


def create_plugin() -> MaiTRPGPlugin:
    return MaiTRPGPlugin()
