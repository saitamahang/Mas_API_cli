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
| **查模型资产时，若用户做训练或未明确说明用途，一律加 `--source Preset`**（3.12.3 list-ext 接口加 `--source Preset`，3.12.1 list 加 `--source Preset`） | 训练前提是基于平台预置基础模型；用户自训/订阅模型只在用户明确要"基于已有产物继续训"时才查 |
| 列表分页：要"全部"加 `--all`；按页用 `--limit/--page` | 默认只取一页（20 条） |
| 写操作（create/deploy/import/publish）能 `--dry-run` 就先 dry-run | 检查请求体合法性而不真正调用 |
| 复杂请求体走 YAML：`-f file.yaml` + 命令行覆盖 | `examples/` 下有现成模板可改 |
| `obs_path` **不要带 `obs://` 前缀**，CLI 已自动剥离但建议一开始就传 `bucket/path/` | API 不接受 `obs://` 协议头 |
| 环境切换：HCS（默认）vs HC，通过 `pangu config set env_type HC/HCS` | HC 接口入参与 HCS 不一致（如 `--job-type` HCS 用 `Train/Infer`，HC 用 `train/infer`） |
| **严禁混用** `pangu model get` 与 `pangu training model-detail` | `model get`（3.12.2）返回资产元数据（asset_name / model_type 等），**不能用于构造训练请求体**；获取训练参数模板（含 workflow_info）必须用 `training model-detail`（3.13.11），后者才是 `create` 的 `task_parameter` 来源。训练场景如 agent 误用 `model get` 会导致参数缺失，100% 创建失败。 |
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

## 2. 数据管理（Dataset） — 以 **CV 图像分类** 为例

> 主键 = `数据集名称 + catalog`（catalog ∈ `ORIGINAL` 原始 / `PROCESS` 加工 / `PUBLISH` 发布）。

### 2.1 列出 / 查询
```bash
pangu dataset list --modal IMAGE -o json                               # 仅看图像数据集
pangu dataset list --catalog ORIGINAL --modal IMAGE --status ONLINE -o json
pangu dataset list --all --modal IMAGE -o json                         # 拉全量
pangu dataset get <dataset_name> --catalog ORIGINAL -o json            # 详情走 v1（v2 缺 dataset_id）
pangu dataset get-by-ids <id1> <id2> -o json
```

### 2.2 从 OBS 导入（CV 图像分类示例）
```bash
# 图像分类：content_type=IMAGE_CLASSIFICATION，file_format 会自动补成 IMAGE_TXT
pangu dataset import \
  --name flower-cls-v1 \
  --obs-path my-bucket/cv/flower/         # 不带 obs:// 前缀
  --content-type IMAGE_CLASSIFICATION
```
图像类 5 种 `content_type` ↔ `file_format` 已硬绑定，未传 `--file-format` 会自动补齐：
| 场景 | content_type | file_format（自动） |
|---|---|---|
| 图像目标检测 | `IMAGE_OBJECT_DETECTION` | `PASCAL` |
| **图像分类（CV 默认示例）** | `IMAGE_CLASSIFICATION` | `IMAGE_TXT` |
| 图像异常检测 | `IMAGE_ANOMALY_DETECTION` | `IMAGE_TXT` |
| 图像语义分割 | `IMAGE_SEMANTIC_SEGMENTATION` | `IMAGE_PNG` |
| 图像实例分割 | `IMAGE_INSTANCE_SEGMENTATION` | `IMAGE_XML` |

复杂场景走 YAML：`pangu dataset import -f examples/dataset_import.yaml --wait`

### 2.3 发布（合并多个原始数据集为训练用数据集）
```bash
# 把多份 CV 分类原始数据集合并发布成一份 PANGU 格式可训练数据集
pangu dataset publish \
  --publish-name flower-cls-train-v1 \
  --source-name flower-cls-v1 --source-name flower-cls-v2 \   # 可多次传入
  --source-catalog ORIGINAL \
  --file-content-type IMAGE_CLASSIFICATION
# CLI 会按名称自动查询每个 source 的 dataset_id 并补入 datasets[]
# --publish-format 默认 PANGU
```

### 2.4 加工
```bash
pangu dataset process --source-name flower-cls-v1 -f examples/dataset_process.yaml
pangu dataset operators --modal IMAGE -o json   # 列 CV 可用算子
```

### 2.5 删除 / 清除
```bash
pangu dataset delete <name1> <name2> --catalog ORIGINAL    # 软删除
pangu dataset purge  <name> --catalog ORIGINAL --delete-obs -y   # 不可恢复
```

---

## 3. 创建训练任务（Training） — 以 **CV 图像分类微调** 为例

> **核心三步：scaffold → dry-run → create**。这是 skill 友好的标准流。

### 3.1 准备前置信息（CV 场景默认查预置模型）

**🚨 第一步必须调 `training model-detail` 拿训练参数模板（不是 `model get`！）**

```bash
# ⚠️ 训练 / 未明确说明用途时，模型查询都加 --source Preset，只看预置基础模型
pangu model list --type CV --source Preset -o json
pangu model list --type CV --source Preset --sub-type IC -o json     # CV 子类型 IC=图像分类
pangu model list-ext --type CV --source Preset --asset-action SFT -o json  # 带能力判定，拿 model_id

# 🚨 获取训练参数模板 —— 必须用 training model-detail（3.13.11），返回 workflow_info 用于构造 create 请求体
# ❌ 严禁用 pangu model get（3.12.2）代替 —— 后者只返回资产元数据，不含 workflow_info / parameters
pangu training model-detail \
  --model-id <asset_id> --model-type CV --train-type SFT --model-source SYSTEM \
  -o json

pangu pool list -o json                            # 拿 pool_id（HC 需 --job-type/--use-type/--chip-type）
```
**CV 子类型（`--sub-type`）速查**：
`IC`(图像分类) / `SS`(语义分割) / `ED`(事件检测) / `OVD`(万物检测) / `PE`(姿态估计) /
`AD`(异常检测) / `ObjectDetection`(物体检测) / `OpticalCharacterRecogniton`(OCR) /
`OpenVocabularySegmentation`(万物分割) / `RD`(旋转检测)

### 3.2 scaffold 生成请求体骨架（推荐）
```bash
pangu training scaffold \
  --asset-id <asset_id> \
  --model-id <model_id> \
  --model-type CV \
  --train-type SFT \
  --model-source SYSTEM \
  --out train.yaml
# ⚠️ scaffold 的 --model-source 是 3.13.11 model-detail 接口的取值：SYSTEM (盘古预置) | USER (训练产物)
# 而 3.13.5 create 接口的 model_source 是另一套：pangu | third | pangu-third (盘古预置三方)
# 严格按各自接口的取值范围使用，不能混用
# scaffold 写入 YAML 时按 SYSTEM→pangu / USER→third 自动映射；如属于盘古预置三方模型加 --create-model-source pangu-third
# 内部会调 model-detail，把 workflow_info.parameters 填到 task_parameter
# scaffold 会按 env_type 生成不同骨架：
#   HCS：顶层 resource_config + pool_node_count / flavor / t_flops
#   HC ：把 train_flavor 注入 task_parameter.parameters[name=train_flavor].value = {flavor, pool_id}
# 然后人工/agent 编辑 train.yaml 的 TODO 占位符（task_name / pool_id / chip_type/flavor_id 或 train_flavor 等）
```
> 不想写文件就去掉 `--out`，直接打印到 stdout 由 agent 接管。

#### 资源池注入方式（必读，HCS / HC 不同）

| env_type | 写入位置 | CLI 参数 |
|---|---|---|
| HCS | 顶层 `resource_config` + `pool_node_count` / `flavor` / `t_flops` | `--pool-id --pool-type --chip-type --flavor-id --nodes --flavor [--t-flops]` |
| HC  | `task_parameter.parameters` 中的 `train_flavor` 超参（`value = {flavor, pool_id}`） | `--pool-id --train-flavor "<规格>"` |

HC 模式下 `--pool-type / --chip-type / --flavor-id / --nodes / --flavor / --t-flops` 全部不生效（CLI 会忽略并给出警告）。`--train-flavor` 取自 `pangu training model-detail` 返回的规格表，例 `1*ascend-snt9b`。

> **重要**：HC 下 `model-detail` 的 `workflow_info.parameters` 里**已经有 `train_flavor` 项**，只是相较其他超参缺 `default`。CLI 在 inject 时会保留原项的 description/type/required 等字段，仅补/覆盖 `value = {flavor, pool_id}`。pool_id 仍由 `pangu pool list` 获取，和 HCS 一样。

> **参数定义 → 运行时值的转换**：`model-detail` 返回的 `workflow_info.parameters` 是参数*定义*（含 `default / constraint / enum / type` 等元信息），但 3.13.5 创建请求体里每条参数还要带 `value` 字段（PDF §3.13.5 请求示例显示 `default` 与 `value` 同时存在，`value` 通常 = `default`）。`scaffold` 已自动转换：
> - `format == "train_flavor"` → `value = {"flavor_id": "TODO", "pool_id": "TODO"}`（HC 后续由 `--pool-id/--train-flavor` 覆盖）
> - `format ∈ {"nfs","pfs"}` → 不写 `value`（多为可选挂载/监控目录，按需自填）
> - 有 `default` → `value = default`
> - 其余 → `value = "TODO-请按描述填值"`
>
> `task_parameter` 是 `workflow_info` 的**完整副本**（不只 `parameters`/`storages`/`data_requirements`，还包含 `extend`/`assets`/`data`/`steps`/`policy` 等模型特有字段），scaffold 已完整带过去。

#### scaffold 已覆盖的可选字段（PDF §3.13.5 全集）
模板会列出全部顶层可选字段（不需要的请删除/留空）：
- 数据集：`dataset_*` / `eval_*` / `dataset_split_ratio`
- 断点续训：`checkpoint_id` / `checkpoint_config{save_checkpoints_max, skipped_steps, restore_training, checkpoint_publish_info}`
- SFS Turbo（HCS）：`sfs_config{model_sfs_enable, dataset_sfs_enable, dataset_preload}`
- 量化：`output_artifact_name` / `quantization_type`
- RLHF：`reward_model_id`（接口当前注明"不支持"，占位）
- 三方模型环境变量：`task_env`（model_source=third/pangu-third 用）
- 日志：`plog_level` / `is_input_finished`
- 资源（HCS）：`resource_config{pool_type, chip_type, pool_id, pool_name, flavor_id, flavor_name, node_count, fp16, t_flops, training_unit}`
- 训练参数：`task_parameter{parameters[每条带 value], storages, data_requirements}`
> `create` 提交前会递归剔除 `null` 字段（scaffold 留下未填的 `None` 占位不会发到 API），但保留空字符串 / 空对象 / 空数组。

### 3.3 dry-run 校验
```bash
pangu training create -f train.yaml --dry-run
# 输出最终请求体 YAML，含必填校验
#   HCS：t_flops 自动推导（nodes × flavor_id × flavor）
#   HC ：校验 task_parameter.parameters 中存在 train_flavor 且 pool_id 非空
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
pangu training metrics <task_id> --model-type CV -o json    # ⚠️ -o json，否则是终端可视化
pangu training logs <task_id> --node worker-0
pangu training nodes <task_id> -o json
pangu training checkpoints <task_id> -o json
pangu training stop <task_id>
```

### 3.6 必填字段（create）
| 字段 | 来源 |
|---|---|
| `asset_id` | `pangu model list --source Preset`（训练默认查预置） |
| `task_name` | 自取，如 `cv-flower-cls-sft-v1` |
| `model_type` | CV（本示例）/ NLP / MM / Predict / AI4Science |
| `train_type` | SFT / PRETRAIN / LORA / DPO / RFT |
| `model_source` | **两套不同枚举，严格区分**：`scaffold` / `model-detail` (3.13.11) 用 `SYSTEM` (盘古预置) / `USER` (训练产物)；`create` (3.13.5) 写入 YAML 的是 `pangu` / `third` / `pangu-third` (盘古预置三方)。scaffold 自动映射 SYSTEM→pangu / USER→third；如属于盘古预置三方模型显式 `--create-model-source pangu-third` |
| `t_flops` | **[HCS 必填]** 可省，CLI 按 `nodes × flavor_id × flavor` 自动推导。**HC 不需要此字段** |
| 资源池 | HCS：`resource_config.{pool_id,pool_type,chip_type,flavor_id}`；HC：`task_parameter.parameters[train_flavor].value.{flavor,pool_id}` |
| `task_parameter` | 由 scaffold 从 `model-detail.workflow_info` **完整复制**（含 `parameters`+`storages`+`data_requirements`+`extend`+`assets`+`data`+`steps`+`policy` 等全部字段；其中 `parameters` 的每条 parameter 自动补 `value`；HC 下还会注入 `train_flavor` 占位） |

### 3.7 训练完成后发布为模型资产
```bash
pangu training publish <task_id> --asset-name flower-cls-sft-v1 --visibility current
# --category 默认 pangu，三方模型用 --category 3rd
```

---

## 4. 部署为推理服务（Service） — 以 **CV 图像分类模型部署** 为例

### 4.1 列表 / 详情
```bash
pangu service list -o json
pangu service list --status running --type CV -o json
pangu service get <service_id> -o json
```

### 4.2 部署
```bash
# 推荐 YAML 模板：examples/service_deploy.yaml
pangu service deploy -f examples/service_deploy.yaml --wait

# 命令行（CV 推理服务示例）
pangu service deploy \
  --name flower-cls-svc \
  --model-id <asset_id>           # 取自上一节训练后 publish 的 asset_id，
                                  # 或预置 CV 模型：pangu model list --type CV --source Preset
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
| 模型列表返回过多无关项（用户/订阅/导入混杂） | 训练或未明确说明用途时，加 `--source Preset` 只查预置基础模型 |
| `obs_path` 报格式错误 | 把 `obs://bucket/path/` 改成 `bucket/path/`（CLI 会自动剥离，但建议直接传对） |
| 创建训练任务报缺 `task_parameter` | 必走 `scaffold` 取模板；不要手写 |
| `metrics` 输出乱码方块 | 终端字体没装 Braille，加 `-o json` 取原始数据 |
| HC 资源池查询返回空 | 三个必填没传齐：`--job-type train/infer` `--use-type private` `--chip-type D910B3`（CLI 不会代为补默认） |
| `model-detail` 返回 JSON 太大被截断 | 计划支持 `--section`，当前先 `-o json | jq '.workflow_info.parameters'` 自行过滤 |
| 数据发布返回 dataset_id 缺失 | CLI 已按 `--source-name` 自动查 v1 详情补 ID；若 v2 detail 用过头，注意主键 `name+catalog` |
| CV 训练找不到合适模型 | 用 `pangu model list --type CV --source Preset --sub-type IC` 按子类型 (IC/SS/OVD/...) 缩小范围 |

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
