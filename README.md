# pangu-cli

盘古平台 CLI 与 agent 工作流工具。安装后提供两个入口:

| 命令 | 定位 | 适合场景 |
|------|------|----------|
| `pangu` | 原始平台管理 CLI，直接封装工作空间、模型资产、数据集、训练任务、推理服务等能力 | 人工操作、脚本、排障、底层 API 验证 |
| `pangu-agent` | 面向 AI agent 的安全工作流 CLI，在 `pangu` 之上增加结构化输出、目标边界、审批门禁、分页候选和异步监控 | Codex、Claude、其他 agent 执行训练/部署流程 |

详细文档:

- [pangu CLI 命令参考](docs/pangu-cli-reference.md)
- [pangu-agent 使用指南](docs/pangu-agent-usage.md)
- [pangu-agent 设计文档](docs/pangu-agent-design-v2.md)

## 安装

推荐直接安装当前项目:

```bash
pip install -e .
```

也可以使用 `requirements.txt`:

```bash
pip install -r requirements.txt
```

`requirements.txt` 会安装当前项目，并读取 `pyproject.toml` 中声明的依赖。

安装后可以使用:

```bash
pangu --help
pangu-agent --help
```

## 共享配置

`pangu` 和 `pangu-agent` 共用 `~/.pangu/config.yaml`。

初始化配置:

```bash
pangu config init
```

常用配置:

```bash
pangu config set default_workspace_id <workspace_id>
pangu config set env_type HCS
pangu config set use_system_proxy false
pangu config set monitor_adapter codeagent
```

Token 模式登录:

```bash
pangu auth login
pangu auth status
```

API Key 模式在 `pangu config init` 时选择 `apikey` 并配置 API Key，无需手动登录。

## 什么时候用 pangu

`pangu` 是底层平台管理入口，适合直接查看或操作单个资源:

```bash
pangu workspace list
pangu model list-ext --name-snip Pangu
pangu dataset list --catalog PUBLISH --status ONLINE
pangu training get <task_id>
pangu service get <service_id>
```

完整命令见 [pangu CLI 命令参考](docs/pangu-cli-reference.md)。

## 什么时候用 pangu-agent

`pangu-agent` 是给 agent 使用的工作流入口。它的核心目标是降低 agent 乱猜参数、跳过确认、输出截断、长时间轮询等风险。

它提供:

- JSON-only 结构化输出和明确 `next_action`
- `goal` 目标边界，避免自动越权发布或部署
- validate / approve / submit 三段式门禁
- 候选分页和详情命令，减少工具输出截断影响
- 训练和部署的 detached monitor，避免主会话长时间轮询

基本检查:

```bash
pangu-agent doctor --json
pangu-agent scenarios --json
```

训练规划示例:

```bash
pangu-agent train plan \
  --scenario cv_object_detection \
  --goal training_completed \
  --json
```

部署到运行态示例:

```bash
pangu-agent deploy plan \
  --asset-id <asset_id> \
  --goal service_running \
  --json

pangu-agent deploy submit \
  --run-id <run_id> \
  --session-id <session_id>
```

当 `goal` 超过 submitted 阶段且提供了 `session_id` 时，`train submit` / `deploy submit` 会在提交成功后直接创建 detached monitor，并返回 `monitor_created: true`。主会话应停止等待，由 monitor 在训练或部署到终态后把消息投递回来源会话。

完整流程见 [pangu-agent 使用指南](docs/pangu-agent-usage.md)。

## Agent 使用约束

让 agent 执行训练或部署时，优先要求它使用 `pangu-agent`，不要直接调用底层 `pangu training` / `pangu service` 做长轮询。

推荐描述:

```text
使用 pangu-agent 帮我提交部署，目标是等服务 running。
提交后创建异步 monitor，不要在主会话里轮询，部署成功或失败后通知我。
```

如果只是人工排障、查看单个资源或验证底层接口，再使用 `pangu`。
