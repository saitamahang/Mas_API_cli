---
name: pangu
description: 操作华为盘古大模型平台 (Pangu LLM) — 数据集导入/发布/加工、训练任务创建/监控、模型部署为推理服务。当用户提到 pangu / 盘古 / 数据集 / 训练任务 / 推理服务 / model-train / inference-service，或要求"在盘古平台上"做数据/训练/部署时调用。底层走本仓 `pangu` CLI。
---

# Pangu 平台 CLI Skill

通过本仓 `pangu` 命令完成 **数据管理 / 训练任务 / 推理服务部署** 三类操作。所有命令以 `pangu ...` 形式经 Bash 执行，调用前请先确认 CLI 已可用 (`pangu --version` 或 `which pangu`)。

完整命令、枚举、示例见仓库根的 `README.md`；本 SKILL 只列 **agent 必须遵守的约定** 和 **三大场景的最小可行流程**。

---

## 0. 通用约定（强制）

| 约定 | 原因 |
|---|---|
| **总是加 `-o json`** 取 list/get 类输出 | agent 解析 JSON 比表格稳，不会被颜色/对齐字符干扰 |
| **`metrics` 用 `-o json`**（默认是 chart 可视化） | chart 是给人看的 Braille 曲线 + 进度条 |
| 列表分页：要"全部"加 `--all`；按页用 `--limit/--page` | 默认只取一页（20 条） |
| 写操作（create/deploy/import/publish）能 `--dry-run` 就先 dry-run | 检查请求体合法性而不真正调用 |
| 复杂请求体走 YAML：`-f file.yaml` + 命令行覆盖 | `examples/` 下有现成模板可改 |
| `obs_path` **不要带 `obs://` 前缀**，CLI 已自动剥离但建议一开始就传 `bucket/path/` | API 不接受 `obs://` 协议头 |
| 环境切换：HCS（默认）vs HC，通过 `pangu config set env_type HC/HCS` | HC 接口入参与 HCS 不一致（如 `--job-type` HCS 用 `Train/Infer`，HC 用 `train/infer`） |
| 工作空间不显式传 `-w` 时使用默认 workspace；可 `pangu config use-workspace <id>` 切换 | 多空间环境务必先确认 |

> 凡是命令报错或返回 4xx/5xx，**先回显 stderr 给用户、再分析**，不要静默重试。

---

## 1. 环境准备（一次性）

```bash
pangu config init          # 交互式；非交互见 README "非交互式" 段
pangu auth login           # Token 模式登录（或配置 API Key）
pangu auth status          # 确认登录态
pangu workspace list -o json
pangu config use-workspace <workspace_id>   # 切默认空间
```

如果用户给了 endpoint / domain / project_id / workspace_id，优先用 `pangu config init -n` 一次性写入。

---

## 2. 数据管理（Dataset）

> 主键 = `数据集名称 + catalog`（catalog ∈ `ORIGINAL` 原始 / `PROCESS` 加工 / `PUBLISH` 发布）。

### 2.1 列出 / 查询
```bash
pangu dataset list -o json                                          # 第一页
pangu dataset list --all -o json                                    # 拉全部
pangu dataset list --catalog ORIGINAL --modal TEXT -o json
pangu dataset get <dataset_name> --catalog ORIGINAL -o json         # 详情走 v1（v2 缺 dataset_id）
pangu dataset get-by-ids <id1> <id2> -o json
```

### 2.2 从 OBS 导入
```bash
pangu dataset import \
  --name <name> \
  --obs-path bucket-name/path/             # 不带 obs:// 前缀
  --content-type <CT> \
  --file-format <FF>                       # 见下方 CT↔FF 自动补齐表
```
图像类 5 种 `content_type` ↔ `file_format` 已硬绑定，未传 `--file-format` 会自动补齐：
| content_type | file_format |
|---|---|
| `IMAGE_OBJECT_DETECTION` | `PASCAL` |
| `IMAGE_CLASSIFICATION` | `IMAGE_TXT` |
| `IMAGE_ANOMALY_DETECTION` | `IMAGE_TXT` |
| `IMAGE_SEMANTIC_SEGMENTATION` | `IMAGE_PNG` |
| `IMAGE_INSTANCE_SEGMENTATION` | `IMAGE_XML` |

复杂场景走 YAML：`pangu dataset import -f examples/dataset_import.yaml --wait`

### 2.3 发布（合并多个原始数据集）
```bash
pangu dataset publish \
  --publish-name <new_name> \
  --source-name ds-a --source-name ds-b \         # 可多次传入
  --source-catalog ORIGINAL \
  --file-content-type SINGLE_QA
# CLI 会按名称自动查询每个 source 的 dataset_id 并补入 datasets[]
# --publish-format 默认 PANGU
```

### 2.4 加工
```bash
pangu dataset process --source-name <name> -f examples/dataset_process.yaml
pangu dataset operators -o json   # 列可用算子
```

### 2.5 删除 / 清除
```bash
pangu dataset delete <name1> <name2> --catalog ORIGINAL    # 软删除
pangu dataset purge  <name> --catalog ORIGINAL --delete-obs -y   # 不可恢复
```

---

## 3. 创建训练任务（Training）

> **核心三步：scaffold → dry-run → create**。这是 skill 友好的标准流。

### 3.1 准备前置信息
```bash
pangu model list --type NLP -o json                # 拿 asset_id
pangu model list-ext --asset-action SFT -o json    # 拿 model_id（带能力判定）
pangu pool list -o json                            # 拿 pool_id（HC 需 --job-type/--use-type/--chip-type）
```

### 3.2 scaffold 生成请求体骨架（推荐）
```bash
pangu training scaffold \
  --asset-id <asset_id> \
  --model-id <model_id> \
  --model-type NLP \
  --train-type SFT \
  --model-source SYSTEM \
  --out train.yaml
# 内部会调 model-detail，把 workflow_info.parameters 填到 task_parameter
# 然后人工/agent 编辑 train.yaml 的 TODO 占位符
```
> 不想写文件就去掉 `--out`，直接打印到 stdout 由 agent 接管。

### 3.3 dry-run 校验
```bash
pangu training create -f train.yaml --dry-run
# 输出最终请求体 YAML，含必填校验、t_flops 自动推导（nodes × flavor_id × flavor）
# 不会真的调 API
```

### 3.4 真正提交
```bash
pangu training create -f train.yaml
pangu training create -f train.yaml --wait        # 阻塞等到完成/失败/停止
```

### 3.5 任务监控
```bash
pangu training get <task_id> -o json
pangu training metrics <task_id> --model-type NLP -o json   # ⚠️ -o json，否则是终端可视化
pangu training logs <task_id> --node worker-0
pangu training nodes <task_id> -o json
pangu training checkpoints <task_id> -o json
pangu training stop <task_id>
```

### 3.6 必填字段（create）
| 字段 | 来源 |
|---|---|
| `asset_id` | `pangu model list` |
| `task_name` | 自取 |
| `model_type` | 用户/任务定义 (NLP/MM/CV/Predict/AI4Science) |
| `train_type` | SFT/PRETRAIN/LORA/DPO/RFT |
| `model_source` | SYSTEM 或 USER |
| `t_flops` | 可省，CLI 会按 `nodes × flavor_id × flavor` 自动推导 |
| `task_parameter` | 由 scaffold 从 `model-detail.workflow_info.parameters` 填好 |

### 3.7 训练完成后发布为模型资产
```bash
pangu training publish <task_id> --asset-name my-model-v1 --visibility current
# --category 默认 pangu，三方模型用 --category 3rd
```

---

## 4. 部署为推理服务（Service）

### 4.1 列表 / 详情
```bash
pangu service list -o json
pangu service list --status running --type NLP -o json
pangu service get <service_id> -o json
```

### 4.2 部署
```bash
# 推荐 YAML 模板：examples/service_deploy.yaml
pangu service deploy -f examples/service_deploy.yaml --wait

# 或命令行 (字段较多，复杂场景仍建议 YAML)
pangu service deploy \
  --name my-service \
  --model-id <asset_id> \
  --instances 1 \
  --flavor <flavor>
```

### 4.3 生命周期 / 监控
```bash
pangu service start  <service_id>
pangu service stop   <service_id>
pangu service update <service_id> --instances 2
pangu service delete <service_id>

pangu service logs       <service_id>
pangu service node-logs  <service_id> <node_id>
pangu service monitor    <service_id>
pangu service usage      <service_id> --start-time 2024-01-01T00:00:00 --end-time 2024-01-31T23:59:59
pangu service tasks      -o json
```

---

## 5. 排错速查

| 现象 | 原因 / 处理 |
|---|---|
| `obs_path` 报格式错误 | 把 `obs://bucket/path/` 改成 `bucket/path/`（CLI 会自动剥离，但建议直接传对） |
| 创建训练任务报缺 `task_parameter` | 必走 `scaffold` 取模板；不要手写 |
| `metrics` 输出乱码方块 | 终端字体没装 Braille，加 `-o json` 取原始数据 |
| HC 资源池查询返回空 | 三个必填没传齐：`--job-type train/infer` `--use-type private` `--chip-type D910B3`（CLI 不会代为补默认） |
| `model-detail` 返回 JSON 太大被截断 | 计划支持 `--section`，当前先 `-o json | jq '.workflow_info.parameters'` 自行过滤 |
| 数据发布返回 dataset_id 缺失 | CLI 已按 `--source-name` 自动查 v1 详情补 ID；若 v2 detail 用过头，注意主键 `name+catalog` |

---

## 6. 完整命令地图（速查）

| 模块 | 子命令 | 文档 |
|---|---|---|
| 配置 | `pangu config {init,set,use-workspace}` | README §配置 |
| 认证 | `pangu auth {login,status}` | README §认证 |
| 工作空间 | `pangu workspace {list,get,create,update,delete}` | README §工作空间 |
| 资源池 | `pangu pool list` (HCS/HC 自动适配) | README §资源池 |
| 模型资产 | `pangu model {list,get,list-ext,export,export-tasks}` | README §模型资产 |
| 推理服务 | `pangu service {list,get,deploy,update,start,stop,delete,logs,node-logs,monitor,tasks,usage}` | README §推理服务 |
| 训练任务 | `pangu training {list,get,scaffold,create,stop,retry,delete,logs,nodes,metrics,checkpoints,publish,models,usage,running,model-detail}` | README §训练任务 |
| 数据集 | `pangu dataset {list,get,get-by-ids,delete,purge,import,publish,process,operators}` | README §数据集 |

更多枚举值、所有可选参数、字段含义 → 仓库根 `README.md`，或 `<command> --help`。
