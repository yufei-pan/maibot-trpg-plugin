"""麦麦跑团 / MaiTRPG 插件主体。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maibot_sdk import Field, MaiBotPlugin, PluginConfigBase

CURRENT_CONFIG_VERSION = "1.0.0"


class PluginSection(PluginConfigBase):
    __ui_label__ = "基础设置"

    enabled: bool = Field(default=True, description="是否启用插件")
    config_version: str = Field(default=CURRENT_CONFIG_VERSION, description="配置版本号")
    maibot_plays: bool = Field(default=True, description="开局时麦麦是否作为玩家自动加入")


class MaiTRPGConfig(PluginConfigBase):
    plugin: PluginSection = Field(default_factory=PluginSection)


class MaiTRPGPlugin(MaiBotPlugin):
    """麦麦跑团插件主体。"""

    config_model = MaiTRPGConfig

    def __init__(self) -> None:
        super().__init__()
        self._plugin_dir = Path(__file__).resolve().parent

    async def on_load(self) -> None:
        self.ctx.logger.info("麦麦跑团插件已加载")

    async def on_unload(self) -> None:
        self.ctx.logger.info("麦麦跑团插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        if scope == "self":
            self.ctx.logger.info("麦麦跑团配置已更新: version=%s", version)


def create_plugin() -> MaiTRPGPlugin:
    return MaiTRPGPlugin()
