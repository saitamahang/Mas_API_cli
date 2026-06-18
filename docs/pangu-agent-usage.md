# pangu-agent 使用指南

`pangu-agent` 是给 AI agent 使用的工作流 CLI。它不替代 `pangu`，而是在 `pangu` 的底层能力之上增加 agent 安全协议:

- 结构化 JSON 输出，包含 `next_action`、`terminal`、`goal` 等字段。
- `goal` 目标边界，避免 agent 因为上下文联想自动发布、部署或继续下一阶段。
- validate / approve / submit 三段式门禁，提交训练和部署前必须展示摘要并获得用户确认。
- 分页候选和详情命令，减少模型、数据集、资源池列表被工具截断后的误选。
- detached monitor，用外部进程等待训练和部署终态，避免 agent 主会话长时间轮询。

## 基本原则

agent 执行工作流时应只使用 `pangu-agent`。

不要让 agent 在工作流中直接调用:

```bash
pangu model ...
pangu dataset ...
pangu pool ...
pangu training ...
pangu service ...
```

底层 `pangu` 命令适合人工排障、脚本和接口验证；agent 工作流应通过 `pangu-agent` 获取受控输出。

## 前置配置

`pangu-agent` 共用 `pangu` 配置:

```bash
pangu config init
pangu auth login
pangu-agent doctor --json
```

异步 monitor 默认 adapter:

```bash
pangu config set monitor_adapter codeagent
```

monitor 投递需要来源会话 ID。可以由 agent 获取后传入:

```bash
--session-id <session_id>
```

也可以放到环境变量:

```bash
export PANGU_MONITOR_SESSION_ID=<session_id>
```

## Goal 边界

`goal` 表示本次工作流允许做到哪一步。

| goal | 含义 |
|------|------|
| `dataset_ready` | 数据集可用于训练 |
| `training_submitted` | 训练任务已提交 |
| `training_completed` | 训练任务完成 |
| `model_published` | 训练产物已发布为模型资产 |
| `deployment_submitted` | 推理服务部署任务已提交 |
| `service_running` | 推理服务进入 running |

默认值是保守的:

- training 默认 `training_submitted`
- deployment 默认 `deployment_submitted`
- dataset 默认 `dataset_ready`

如果用户说“提交训练”或“提交部署”，默认做到 submitted 就停止。

如果用户说“训练完成后通知我”，应使用:

```bash
--goal training_completed
```

如果用户说“部署成功后通知我”或“等服务 running”，应使用:

```bash
--goal service_running
```

## 训练流程

查看支持场景:

```bash
pangu-agent scenarios --json
```

规划训练:

```bash
pangu-agent train plan \
  --scenario cv_object_detection \
  --goal training_completed \
  --json
```

后续根据返回的 `next_action` 选择模型、数据集、资源池，生成训练 YAML:

```bash
pangu-agent train scaffold \
  --run-id <run_id> \
  --model <index> \
  --dataset <index> \
  --pool <index> \
  --task-name <task_name> \
  --cards <1|2|4|8>
```

列出并确认超参数:

```bash
pangu-agent train params --run-id <run_id> --json
pangu-agent train param-get --run-id <run_id> --index <index> --json
```

校验:

```bash
pangu-agent train validate --run-id <run_id> --batch-size 1
```

如果需要覆盖超参数，在 validate 阶段传入:

```bash
pangu-agent train validate \
  --run-id <run_id> \
  --batch-size 4
```

其他超参数只能使用 `train params` 返回的名称或 index:

```bash
pangu-agent train validate \
  --run-id <run_id> \
  --batch-size 4 \
  --param <param_index>=<json_value>
```

展示 `approval_summary`，用户明确批准后再执行:

```bash
pangu-agent train approve --run-id <run_id> --confirm submit-training
```

提交训练。如果目标超过 `training_submitted`，传入 `session_id` 让 CLI 原子创建 monitor:

```bash
pangu-agent train submit --run-id <run_id> --session-id <session_id>
```

如果返回:

```json
{
  "monitor_created": true,
  "next_action": "stop_waiting_in_main_session"
}
```

agent 主会话应停止等待，不能在主会话中循环查询训练状态。

## 部署流程

从模型资产规划部署:

```bash
pangu-agent deploy plan \
  --asset-id <asset_id> \
  --goal service_running \
  --json
```

根据返回候选选择部署选项和资源池，生成部署 YAML:

```bash
pangu-agent deploy scaffold \
  --run-id <run_id> \
  --option <index> \
  --pool <index> \
  --service-name <name> \
  --access-mode ELB
```

校验:

```bash
pangu-agent deploy validate --run-id <run_id>
```

展示 `approval_summary`，用户明确批准后再执行:

```bash
pangu-agent deploy approve --run-id <run_id> --confirm deploy-service
```

提交部署。如果目标是 `service_running`，传入 `session_id` 让 CLI 原子创建 monitor:

```bash
pangu-agent deploy submit --run-id <run_id> --session-id <session_id>
```

返回 `monitor_created: true` 后，agent 主会话应停止等待。不要再启动脚本循环，也不要直接执行:

```bash
pangu service get <service_id>
```

## 异步 Monitor

首选方式是在 `train submit` / `deploy submit` 时传入 `--session-id`，由 submit 命令原子创建 monitor。

如果历史 run 已经提交，但没有创建 monitor，可以补建:

```bash
pangu-agent monitor add \
  --run-id <run_id> \
  --session-id <session_id> \
  --detach \
  --json
```

查看本地 monitor:

```bash
pangu-agent monitor list --json
pangu-agent monitor status --monitor-id <monitor_id> --json
```

如果投递失败，可以导出消息或重试投递:

```bash
pangu-agent monitor message --monitor-id <monitor_id> --json
pangu-agent monitor retry-delivery --monitor-id <monitor_id> --session-id <session_id> --json
```

## Agent 提示词建议

部署到 running:

```text
使用 pangu-agent 帮我提交部署，目标是等服务 running。
提交后创建异步 monitor，不要在主会话里轮询，部署成功或失败后通知我。
```

训练到完成:

```text
使用 pangu-agent 帮我提交训练，目标是训练完成后通知我。
提交后创建异步 monitor，不要在主会话里轮询。
```

只提交，不等待终态:

```text
使用 pangu-agent 帮我提交训练任务，只需要提交成功，不需要等待训练完成。
```

## 设计文档

更详细的架构、状态机和 adapter 方案见 [pangu-agent 设计文档](pangu-agent-design-v2.md)。
