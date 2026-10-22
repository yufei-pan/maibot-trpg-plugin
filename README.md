# 麦麦跑团 / MaiTRPG

> 让麦麦在群聊里主持并参与一场跑团（TRPG）。

## 概念：双脑 + 引擎

本插件采用**三层协作**架构：

1. **麦麦（MaiBot）作为普通玩家** -- 开局自动加入（`maibot_plays = true`），用自然语言行动，和真人玩家一起推进剧情。
2. **独立 GM 智能体** -- 通过 `ctx.llm.generate` 调用大语言模型，负责场景描写、NPC 扮演和剧情裁定，绝不替玩家做决定。
3. **确定性 Python 引擎** -- 做规则裁判：权威骰子（`trpg_dice`）、属性 schema 校验（`trpg_schema`）、就绪门禁（`trpg_session`）、批处理回合收集（`trpg_batch`）、防失控守卫、审计日志。

引擎保证 GM 不能伪造骰值 -- GM 用 `===ROLL===` 协议请求掷骰，引擎权威掷骰并把结果作为系统回合注入后让 GM 再次生成叙事。

## 工具一览

工具按 `tool_search` 前 5 命中上限分前缀命名，每类不超过 4 个：

### `session_`（会话管理）

| 工具 | 简介 |
|------|------|
| `session_create` | 【麦麦跑团/MaiTRPG·会话】在本聊天新建一场跑团会话（初始 setup，需补全 bible 与角色卡后才能开始）。 |
| `session_list` | 【麦麦跑团/MaiTRPG·会话】列出本聊天的所有会话及状态（含已停止、可重启的会话）。 |
| `session_start` | 【麦麦跑团/MaiTRPG·会话】开始/重启一场会话 -- 会先跑就绪门禁，未通过则报告缺什么。 |
| `session_stop` | 【麦麦跑团/MaiTRPG·会话】停止当前会话（可日后 session_start 重启，会再次跑门禁）。 |

### `bible_`（设定与门禁）

| 工具 | 简介 |
|------|------|
| `bible_world` | 【麦麦跑团/MaiTRPG·设定】写入/追加世界设定到 bible（可多次累积）。 |
| `bible_plot` | 【麦麦跑团/MaiTRPG·设定】写入/追加剧情与钩子到 bible。 |
| `bible_gm` | 【麦麦跑团/MaiTRPG·设定】写入本场 GM 子提示词（基调/主题/特殊裁定；就绪门禁项）。 |
| `bible_check` | 【麦麦跑团/MaiTRPG·设定】检查就绪门禁是否通过（世界/剧情/GM子提示词/属性schema/全员角色卡）。 |

### `sheet_`（角色卡）

| 工具 | 简介 |
|------|------|
| `sheet_schema` | 【麦麦跑团/MaiTRPG·角色卡】查看或设置属性 schema（mode: view/default/custom/edit）。 |
| `sheet_edit` | 【麦麦跑团/MaiTRPG·角色卡】设置某玩家角色卡字段（按 schema 校验类型）。 |
| `sheet_render` | 【麦麦跑团/MaiTRPG·角色卡】渲染某玩家角色卡为图片并发到聊天。 |
| `sheet_mugshot` | 【麦麦跑团/MaiTRPG·角色卡】把图片（data URI/base64）设为某玩家角色卡头像。 |

## 命令（面向人类玩家）

| 命令 | 说明 |
|------|------|
| `/session create <标题>` | 新建会话 |
| `/session list` | 列出当前聊天所有会话 |
| `/session start [会话ID]` | 开始/重启会话（跑就绪门禁） |
| `/session stop [会话ID]` | 停止会话 |
| `/join` | 加入当前会话（加入后需完成角色卡） |
| `/gm go` | 立即把当前台面交给 GM 结算（不等静默超时） |
| `/ooc <文字>` 或 `(( 文字 ))` | 场外发言（OOC），不会进入 GM 回合 |
| `/do <动作>` / `/say <台词>` | 动作/对话前缀（前缀会被清洗后送入批处理） |

## 运行回合机制

### 批处理 + 静默防抖

玩家（包括麦麦）的行动发言会被缓冲到 `BatchBuffer` 中。当台面静默超过 `inactivity_flush_seconds`（默认 45 秒）后自动冲刷，把整批行动交给 GM 生成叙事。也可以用 `/gm go` 立即触发。

### 防失控守卫

当没有真人行动时，允许的最大连续自动推进次数受 `max_consecutive_auto`（默认 2）约束。超过上限则暂停，等待真人玩家行动。

### GM 叙事与发送

GM 旁白以 `【GM】` 前缀直接发送到聊天（`ctx.send.text`，带 `sync_to_maisaka_history=True`），同步进麦麦的聊天历史，规划器和回复器都能看到。发送后通过 `ctx.maisaka.proactive.trigger` 唤醒麦麦以玩家身份回应。（宿主 1.3.12 起 `ctx.maisaka.context.append` 注入的内容只进规划器、回复器看不到，所以旁白不再走它。）

### 掷骰协议

1. GM 在叙事中输出 `===ROLL===` 区块请求掷骰（包含 actor、modifier、dc、advantage、reason）。
2. 引擎用确定性 `trpg_dice.check()` 权威掷骰（d20 + modifier vs DC，支持优势/劣势）。
3. 掷骰结果写入 `audit.log` 并作为系统回合注入上下文，GM 再次生成最终叙事。

### `===WORLD_STATE===` 局势更新

GM 可在叙事中用 `===WORLD_STATE=== <新局势> ===END===` 更新当前局势，引擎会持久化到 `world_state.md`。

## 就绪门禁

会话从 `setup` 状态开始，必须满足以下全部条件才能 `session_start`：

- 世界设定（`world.md`）已写入
- 剧情/钩子（`plot.md`）已写入
- GM 子提示词（`gm_subprompt.md`）已写入
- 属性 schema（`stat_schema.toml`）存在且有字段定义
- 所有已加入成员的角色卡已完成（按 schema 校验必填字段）

运行中如果有新玩家加入但尚未完成角色卡，会话进入 `story_held` 挂起状态（有 `pending_cards`），暂停剧情推进直到新玩家补全角色卡。

## 存储结构

每个聊天流一个会话目录，位于 `data/<stream_id>/<session_id>/`：

```
data/
  <stream_id>/
    <session_id>/
      session.toml          # 会话元数据（标题/状态/成员/pending_cards）
      state.toml            # 运行时状态（预留）
      world_state.md        # 当前局势（GM ===WORLD_STATE=== 更新）
      audit.log             # 掷骰审计日志
      bible/
        world.md            # 世界设定
        plot.md             # 剧情/钩子
        gm_subprompt.md     # GM 子提示词
        stat_schema.toml    # 属性 schema
      characters/
        <member>.toml       # 角色卡数据
        <member>.mugshot    # 头像 URI
      episodes/
        00.log              # 剧集日志（批次行动 + GM 叙事）
```

所有 TOML 写入使用原子替换（先写 `.tmp` 再 `os.replace`），追加日志直接 append。

## 配置项

配置文件为插件目录下的 `config.toml`（可参考 `config.default.toml`）：

### `[plugin]` 基础设置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 是否启用插件 |
| `config_version` | str | `"1.0.0"` | 配置版本号 |
| `maibot_plays` | bool | `true` | 开局时麦麦是否作为玩家自动加入 |

### `[gm]` GM 设置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `main_gm_prompt` | str | （见默认值） | GM 主提示词（机制与人设，可改） |
| `gm_model` | str | `"replyer"` | GM 智能体模型：任务名或具体模型名 |
| `temperature` | float | `0.8` | GM 叙事温度 |
| `max_tokens` | int | `4000` | 单次 GM 生成最大 token，<=0 交由宿主 |
| `timeout_seconds` | int | `300` | 单次 GM 生成超时（秒），<=0 交由宿主默认值 |

### `[loop]` 回合循环

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `inactivity_flush_seconds` | int | `45` | 台面静默多少秒后自动把发言批处理交给 GM |
| `ooc_marker` | str | `"/ooc"` | 场外发言前缀（也支持 `(( ))` 包裹） |
| `max_consecutive_auto` | int | `2` | 无真人行动时允许的最大连续自动推进次数 |

### `[context]` 上下文

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `char_budget` | int | `120000` | GM 上下文字符预算（bible 置顶，超出裁剪最旧回合） |

### `[storage]` 存储

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `data_dir` | str | `""` | 数据根目录；留空 = 插件目录下 `data/` |

## 重要实现说明

- **Hook 机制**：本插件用 `@HookHandler("chat.receive.after_process")`（入站，捕获人类玩家发言）与 `@HookHandler("send_service.after_send")`（出站，捕获麦麦自己的扮演发言）-- 因为当前宿主把 `EventType.ON_MESSAGE` / `AFTER_SEND` 的事件发射注释掉了，这两个 HookHandler 是实际可用的替代方案。
- **角色卡渲染安全**：对玩家输入做 HTML 转义（`html.escape`），对头像 URI 做 `data:image/` / `https://` 白名单校验，防止 XSS 注入。
- **图片体积控制**：角色卡渲染后用 Pillow 无损重编码为 WebP（仅当更小时替换），减小聊天图片体积，缓解 NapCat action-ack 超时导致的假失败。
- **防失控回环**：`on_after_send` 比对 `_last_narration`，若当前出站消息就是本插件刚发出的 GM 旁白则跳过，避免 GM 旁白被当做麦麦玩家行动。

## 测试

依赖：`tomli-w`、`Pillow`（运行时）；测试无额外依赖。

```bash
# 离线冒烟测试（无需 Host）
PYTHONPATH=.:../maibot-plugin-sdk python tests/smoke_test.py

# 完整测试套件
PYTHONPATH=.:../maibot-plugin-sdk pytest -v
```

测试覆盖：骰子确定性、schema（默认/半自定义/全自定义）、会话门禁 + 新玩家挂起、批处理/防失控守卫、上下文预算裁剪、GM 标记解析、角色卡渲染/WebP 重编码、全部工具（mocked ctx）、完整冲刷管线（叙事 + 权威掷骰注入 + world_state 更新）、manifest 能力声明覆盖。

## 部署

软链到 MaiBot 插件目录：

```bash
ln -s ../../maibot-trpg-plugin MaiBot/plugins/maibot-trpg-plugin
```

插件会在宿主启动时自动加载。首次运行前可复制 `config.default.toml` 为 `config.toml` 并按需修改。

## Phase 2 路线图

- `/dispute` + recall：基于 transcript / audit.log 的争议回溯与回滚。
- 规则书 URL 摄取：从 URL 抓取规则书内容，自动生成 `rules.md` / `stat_schema.toml` / 词典种子。
- 词典工具（`lore_`）：游戏内专有名词解释与索引。
- 地图渲染：Markdown 格式地图 + HTML 渲染输出。
- 剧集滚动摘要：`episodes/` 日志的自动摘要与场景分割。

## License

MIT
