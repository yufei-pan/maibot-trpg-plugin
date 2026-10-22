# Changelog

本文件记录 maibot-trpg-plugin 的版本变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.1.2] - 2026-10-21

### 修复

- GM 旁白改为带 `sync_to_maisaka_history=True` 发送，作为真实聊天消息进入麦麦的历史。宿主 1.3.12 起 `ctx.maisaka.context.append` 注入的内容只进规划器、回复器看不到，扮演玩家的回复因此读不到旁白；旁白不再走 `context.append`，manifest 同步移除不再使用的 `maisaka.context.append` 能力声明

### 变更

- manifest 兼容上限改为实际验证过的范围：宿主 `max_version` 1.99.99 → **1.3.99**，SDK `max_version` 2.99.99 → **2.14.99**（SDK 2.14.0 上测试通过）。插件仓库审核不再接受「永远兼容」式的上限
- SDK 兼容上限 `max_version` 2.14.99 → **2.16.99**：宿主 1.3.14 + SDK 2.16.0 上测试通过（SDK 2.15 / 2.16 只新增能力，无破坏性变更）

## [0.1.1] - 2026-08-01

### 变更

- 将带注释的配置模板改为 `config.default.toml`，运行期 `config.toml` 不再入库
- 在 `create_plugin` / `on_load` 中从模板补齐或恢复 Runner 生成的空壳配置

## [0.1.0] - 2026-06-20

### 新增

- 首次发布：TRPG 会话、掷骰与 GM 回合流程
