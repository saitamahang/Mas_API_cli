# pangu-cli

盘古大模型平台管理 CLI，支持工作空间、模型资产、推理服务、训练任务、数据集等全生命周期管理。

## 安装

```bash
pip install -e .
```

安装后即可使用 `pangu` 命令。

---

## 初始化配置

### 交互式（默认）

```bash
pangu config init
```

按提示填入以下信息：

| 配置项 | 说明 | 示例 |
|--------|------|------|
| endpoint | 平台 API 地址 | `https://pangu.cn-north-7.myhuaweicloud.com` 或 `http://192.168.1.1:8080` |
| iam_endpoint | IAM 认证地址 | `https://iam.cn-north-7.myhuaweicloud.com` 或 `http://192.168.1.1:31943` |
| auth_mode | 认证模式 | `token` 或 `apikey` |
| username | 用户名（token 模式） | `your_username` |
| domain_name | 账号名（token 模式） | `your_domain` |
| project_name | 项目名称（token 模式） | `cn-north-7` |
| project_id | 项目 ID | `abc123...` |
| default_workspace_id | 默认工作空间 ID | `ws-xxx` |

配置保存在 `~/.pangu/config.yaml`，可随时用 `pangu config show` 查看。

### 非交互式（适合脚本 / CI/CD / skill 封装）

```bash
# token 模式
pangu config init -n \
  --endpoint https://pangu.example.com \
  --iam-endpoint https://iam.example.com \
  --username admin \
  --domain-name myorg \
  --project-name cn-north-7 \
  --project-id abc123 \
  --workspace-id ws-xxx \
  --password mypass

# apikey 模式
pangu config init -n \
  --endpoint https://pangu.example.com \
  --auth-mode apikey \
  --api-key your-key \
  --project-id abc123
```

### 测试环境 / 自签名证书

如果 endpoint 是 IP:PORT 形式的测试环境，按以下方式配置：

**HTTP 环境**（endpoint 直接写 `http://`）：
```bash
pangu config set endpoint http://192.168.1.1:8080
pangu config set iam_endpoint http://192.168.1.1:31943
```

**HTTPS + 自签名证书**（关闭证书验证）：
```bash
pangu config set endpoint https://192.168.1.1:8080
pangu config set ssl_verify false
```

### 系统代理问题（Windows 504）

Windows 系统代理会被 httpx 自动读取（注册表 + 环境变量），可能导致对内网地址的请求经过代理后返回 504。在 hosts 里添加忽略无效，需在 CLI 层面关闭代理感知：

```bash
# 完全忽略系统代理（推荐，访问内网环境时使用）
pangu config set use_system_proxy false

# 或显式指定代理地址（走特定代理时使用）
pangu config set proxy http://127.0.0.1:7890

# 恢复使用系统代理
pangu config set use_system_proxy true
pangu config set proxy ""
```

### 单项修改

```bash
pangu config set default_workspace_id ws-new-id
pangu config set timeout 60
```

### 配置登录密码（可选）

配置后执行 `pangu auth login` 无需交互输入密码，适合脚本和 skill 场景。密码以明文存储，注意文件权限。

密码优先级：命令行参数 > 环境变量 `PANGU_PASSWORD` > 配置文件 > 交互输入。

```bash
pangu config set password your_password
```

### 切换环境类型

不同环境的 API 路径和响应格式可能不同，通过 `env_type` 切换适配器：

| 环境 | 说明 |
|------|------|
| `HCS` | HCS 环境（默认），标准嵌套响应格式 |
| `HC`  | HC 环境，平铺响应格式，workspace 通过 Header 传递 |

```bash
pangu config set env_type HC    # 切换到 HC 环境
pangu config set env_type HCS   # 切换到 HCS 环境（默认）
```

### 切换默认工作空间

```bash
pangu config use-workspace ws-xxx
```

---

## 认证

### Token 模式

```bash
pangu auth login

# 通过环境变量传入密码（适合 CI/CD）
PANGU_PASSWORD=your_password pangu auth login

# 配置文件中已设置 password 时直接执行，无需交互
pangu auth login
```

Token 有效期 24 小时，自动缓存在 `~/.pangu/token_cache.yaml`，过期前 5 分钟自动提示重新登录。

### API Key 模式

在 `pangu config init` 时选择 `apikey` 模式并填入 API Key，无需手动 login。

### 查看认证状态

```bash
pangu auth status
```

---

## 命令参考

### 工作空间管理

```bash
# 查询列表
pangu workspace list

# 查看详情
pangu workspace get <workspace_id>

# 新建
pangu workspace create --name my-workspace --description "测试空间"

# 新建（含 OBS 配置）
pangu workspace create --name my-workspace --obs-ak AK --obs-sk SK --obs-bucket my-bucket

# 修改
pangu workspace update <workspace_id> --name new-name

# 删除
pangu workspace delete <workspace_id>
pangu workspace delete <workspace_id> -y   # 跳过确认
```

---

### 资源池管理

资源池命令根据 `env_type` 自动选择对应的 API 和解析逻辑。

**HCS 环境**（默认）：

```bash
pangu pool list
pangu pool list --arch ARM
pangu pool list --job-type Train --status created     # HCS 用大写驼峰：Train | Infer
pangu pool list --job-type Infer
pangu pool list -w <workspace_id>
```

**HC 环境**（需先 `pangu config set env_type HC`）：

```bash
# ⚠️ HC 接口 --job-type / --use-type / --chip-type 三者均为必填，CLI 不会代为补默认值
#    常用默认建议（请在命令行显式传入，不要依赖隐式默认）：
#       --job-type   train | infer    （小写，HC 接口要求）
#       --use-type   private          （建议默认值）
#       --chip-type  D910B3           （建议默认值，可多次传入支持多卡）
#    （HCS 用大写驼峰 Train/Infer，HC 用小写 train/infer，切环境时记得改）
pangu pool list --job-type train --chip-type D910B3 --use-type private
pangu pool list --job-type infer --chip-type D910B3 --use-type poc
```

---

### 模型资产管理

对应 API 3.12.1 ~ 3.12.5。注意 `list` 与 `list-ext` 是两个不同接口，过滤能力和响应结构不同：

```bash
# 3.12.1 查询资产列表（响应为 Array<Array<ModelAsset>>，CLI 已自动展平）
pangu model list                                  # 当前空间全部
pangu model list --type NLP --category pangu      # 按模型类型 + 分类
pangu model list --source Preset                  # 仅预置模型  (Preset|Publish|Import|"AI Hub")
pangu model list --action-type SFT                # 按操作类型 (PRETRAIN|SFT|RLHF|TRANSFORM|QUANTIZATION|EVALUATION|ONLINE-DEPLOY|EDGE-DEPLOY)
pangu model list --sub-type Weather_24h           # 子类型精确匹配（科学计算）
pangu model list --sub-type-snip Weather          # 子类型模糊搜索（仅科学计算生效）
pangu model list --asset-id id1 --asset-id id2    # 多个 asset_id 过滤
pangu model list --asset-code Pangu-NLP-N1-...    # 按模型族谱编码
pangu model list --feature 7B                     # NLP 存储参数量 / 科学计算时间分辨率
pangu model list --user-id <uid> --no-op-user     # 按发布用户过滤（is_op_user=0 必搭配）
pangu model list --workspace-source others        # 来自其他空间 (current|others)

# 3.12.2 查询资产详情
pangu model get <asset_id>
pangu model get <asset_id> --all-actions                     # 展示模型支持的全部 actions
pangu model get <asset_id> --action-asset-tag NLP-N1-PERTRAIN

# 3.12.3 获取完整模型列表（含 can_deploy/can_train/can_eval/is_used 等能力标识）
#   CLI 已把嵌套的 modelAsset.* 展平到顶层，方便表格展示
pangu model list-ext
pangu model list-ext --type NLP,CV --visibility current --sort desc
pangu model list-ext --name-snip Pangu --asset-action SFT,LORA
pangu model list-ext --source AIGallery                      # 订阅模型 (3.12.3 使用 AIGallery，不是 "AI Hub")

# 3.12.4 导出 ModelArts Site 格式（--export-obs-path / --esn 均必填）
pangu model export <asset_id> \
    --export-obs-path obs://my-bucket/export-dir/ \
    --esn G3M3ER2CT32SJ7RYDBB7MFFBKNB77QM7XQQA

# 3.12.5 查询模型迁移/导出任务列表（无 asset_id；覆盖 import/export/publish/subscribe）
pangu model export-tasks
pangu model export-tasks --direction export --status Exporting
pangu model export-tasks --type model --sort-by desc --limit 50
```

---

### 推理服务管理

```bash
# 查询列表
pangu service list
pangu service list --status running --type NLP
pangu service list --name keyword --limit 50

# 查看详情
pangu service get <service_id>

# 部署服务（命令行参数）
pangu service deploy \
  --name my-service \
  --asset-id <asset_id> \
  --asset-type NLP \
  --pool-id <pool_id> \
  --instances 1 \
  --infer-type dedicated

# 部署服务（YAML 配置文件）
pangu service deploy -f examples/service_deploy.yaml

# 部署并等待就绪
pangu service deploy -f examples/service_deploy.yaml --wait

# 更新实例数
pangu service update <service_id> --instances 2

# 启动 / 停止
pangu service start <service_id>
pangu service stop <service_id>

# 删除
pangu service delete <service_id>

# 查看日志
pangu service logs <service_id>
pangu service node-logs <service_id> <node_id>

# 监控指标
pangu service monitor <service_id>

# 全局任务列表
pangu service tasks

# 资源用量
pangu service usage <service_id>
pangu service usage <service_id> --start-time 2024-01-01T00:00:00 --end-time 2024-01-31T23:59:59
```

---

### 训练任务管理

> 训练任务的主键为 `task_id`，状态字段为 `task_status`。
> 日志、节点、指标、断点等命令需要 `execution_id`，工具会自动从任务详情中获取，也可通过 `--execution-id` 手动指定。

**创建训练任务的必填项及来源**（`pangu training create` 校验的字段）：

| 字段 | 来源 / 获取方式 |
|---|---|
| `task_name` | 用户自定义，数字/中文/字母/-/_，≤64 字符，不以数字开头 |
| `asset_id` | `pangu model list` → 选一个模型资产的 `asset_id` |
| `model_id`（NLP/MM 必填） | 预置模型时 = `asset_id`；训练后产物取自 `pangu training models <task_id>` |
| `model_type` | 固定枚举 `NLP / MM / CV / Predict / AI4Science` |
| `train_type` | 固定枚举 `SFT / PRETRAIN / LORA / DPO / RFT`，默认 `SFT` |
| `model_source` | 固定枚举 `pangu / third / pangu-third`（**仅 3.13.5 create 接口** 的取值；不要与 3.13.11 model-detail 的 `SYSTEM/USER` 混用） |
| `t_flops` | **[HCS 必填]** 整数：卡数 × flavor（`pangu pool list` 看 flavor，常见 313 / 280）。HC 模式下不需要此字段 |
| `task_parameter` | 复杂对象，**必须先调 `pangu training model-detail` 取 `workflow_info.parameters` 作模板**，改写后放入 YAML |

> `task_parameter` 结构因 `model_id + train_type` 组合而异（learning_rate / warmup / batch_size / training_flavor / sfs_* 等几十项），不能凭空写。固定流程：`model-detail` → 改参数 → `create`。
>
> ⚠️ **参数定义 vs 运行时值**：`model-detail` 返回的是参数*定义*（含 `default / constraint / enum / type` 等元信息），但 3.13.5 创建请求体里每条参数还需要带一个 `value` 字段（PDF §3.13.5 请求示例显示 `default` 与 `value` 同时存在，且 `value` 通常 = `default`）。`scaffold` 已自动转换：
> - `format == "train_flavor"` 项 → `value = {"flavor_id": "TODO", "pool_id": "TODO"}`
> - `format ∈ {"nfs","pfs"}` 项 → 不写 `value`（多为可选挂载/监控目录，按需自填）
> - 有 `default` 的项 → `value = default`
> - 其余 → `value = "TODO-请按描述填值"`
>
> `task_parameter` 是 `workflow_info` 的**完整副本**（不只 `parameters`/`storages`/`data_requirements`，还包含 `extend`/`assets`/`data`/`steps`/`policy` 等模型特有字段），scaffold 已完整带过去。

#### scaffold 已覆盖的可选字段（PDF §3.13.5 全集）

`scaffold` 生成的 YAML 模板会列出所有可选顶层字段（按需保留/删除/填值）：

- 基础：`task_name` / `asset_id` / `model_id` / `model_type` / `train_type` / `model_source` / `model_name` / `train_task_desc`
- 数据集：`dataset_id` / `dataset_name` / `dataset_version_id` / `eval_*` / `dataset_split_ratio`
- 断点续训：`checkpoint_id` / `checkpoint_config{save_checkpoints_max, skipped_steps, restore_training, checkpoint_publish_info}`
- SFS Turbo 加速（HCS）：`sfs_config{model_sfs_enable, dataset_sfs_enable, dataset_preload}`
- 量化场景：`output_artifact_name` / `quantization_type`
- 强化学习：`reward_model_id`（接口当前注明"不支持"，保留占位）
- 三方模型环境变量：`task_env`（model_source=third/pangu-third 时使用）
- 日志：`plog_level` / `is_input_finished`
- 资源（HCS）：`pool_node_count` / `flavor` / `t_flops` / `resource_config{pool_type, chip_type, pool_id, pool_name, flavor_id, flavor_name, node_count, fp16, t_flops, training_unit}`
- 训练参数：`task_parameter{parameters[每条带 value], storages, data_requirements}`

> `create` 提交前会递归剔除请求体中所有值为 `null` 的字段（scaffold 留下未填的 `None` 占位不会发到 API），但保留空字符串 / 空对象 / 空数组（用户可能有意保留）。

#### 资源池注入方式（随 env_type 不同）

| env_type | 写入位置 | 关键字段 |
|---|---|---|
| **HCS** | 顶层 `resource_config` + `pool_node_count` / `flavor` / `t_flops` | `resource_config.pool_id` / `pool_type` / `chip_type` / `flavor_id` |
| **HC**  | `task_parameter.parameters` 中的 `train_flavor` 超参 | `value = {"flavor_id": "<规格>", "pool_id": "<pool-xxx>"}` |

> HC 下 `pangu training model-detail` 返回的 `workflow_info.parameters` 里**已经包含一个 `train_flavor` 项**，但相较其他超参缺少 `default`。创建任务时只需为该项补 `value`（其他字段 description/type/required 保持不变）。资源池来源仍是 `pangu pool list`，与 HCS 一致。

HC 示例：

```yaml
task_parameter:
  parameters:
    - name: train_flavor
      value:
        flavor: "1*ascend-snt9b"        # 取自 pangu training model-detail 的规格表
        pool_id: "pool-xxxxxxxx"        # pangu pool list 取 pool_id
    # ... 其他超参
```

在命令行可用 `--pool-id <pool-xxx> --train-flavor <规格>` 注入；CLI 会就地更新 `task_parameter.parameters` 中的 `train_flavor` 项（不存在时自动 append）。
HCS 专有的 `--pool-type / --chip-type / --flavor-id / --nodes / --flavor / --t-flops` 在 HC 模式下被忽略并提示。

**核心枚举**（按《训练任务管理 API》权威定义）：

| 字段 | 取值 |
|---|---|
| `--model-type` | `NLP` (NLP大模型) · `MM` (多模态) · `CV` · `Predict` (预测) · `AI4Science` (科学计算) |
| `--train-type` | `SFT` (全量微调) · `PRETRAIN` (预训练) · `LORA` (lora) · `DPO` · `RFT` |
| `--model-source` (create, 3.13.5) | `pangu` (盘古预置) · `third` (三方) · `pangu-third` (盘古预置三方模型) |
| `--model-source` (model-detail / scaffold, 3.13.11) | `SYSTEM` (盘古发布的预置模型) · `USER` (训练任务产生的模型) — **与 create 不同套，严格区分** |
| `--visibility` (publish) | `current` (当前空间) · `all` (全部空间) |
| `--category` (publish) | `pangu` · `3rd` · `pangu-poc` · `pangu-iit` · `3rd-pangu` |
| `--action-type` (models) | `PRETRAIN` · `SFT` · `LORA` · `QUANTIZATION` · `DPO` |
| `--status` (models) | `published` · `unpublished` |
| `--plog-level` | `-1`(不开启) · `0`(info) · `1`(debug) · `2`(warning) · `3`(error) |
| task_status | `init` · `wait_created` · `pending` · `running` · `stopping` · `stopped` · `failed` · `completed` |

```bash
# 查看详情
pangu training get <task_id>

# 推荐流程：先用 scaffold 生成 YAML 模板（内部自动调 3.13.11 model-detail 拉 task_parameter）
# 注意：scaffold/model-detail (3.13.11) 的 --model-source 取值是 SYSTEM | USER
#       create (3.13.5) 的 model_source 取值是 pangu | third | pangu-third
#       两套取值严格区分，不能混用
# scaffold 写入 YAML 时按 SYSTEM→pangu / USER→third 自动映射；如属于"盘古预置三方模型"显式 --create-model-source pangu-third
pangu training scaffold \
  --model-id <model_id> --model-type NLP --train-type SFT --model-source SYSTEM \
  --asset-id <asset_id> \
  --out train.yaml

# 编辑 train.yaml 里的 TODO 字段：
#   HCS：task_name / resource_config.pool_id / chip_type / flavor_id / t_flops（或给齐 nodes+flavor+flavor_id 自动推导）
#   HC ：task_name / task_parameter.parameters[train_flavor].value.{flavor,pool_id}

# 预检请求体（不会发送，skill 调试首选）
pangu training create -f train.yaml --dry-run

# 真实提交
pangu training create -f train.yaml

# 也可直接用 model-detail 看原始返回（含 chip_type 可选值、parameters 约束等）
# 这里 --model-source 用 SYSTEM | USER（盘古预置 / 用户训练产物）
pangu training model-detail \
  --model-id <model_id> --model-type NLP --train-type SFT --model-source SYSTEM

# 命令行覆盖 YAML（HCS 必填: task_name / asset_id / model_type / train_type / model_source / t_flops / task_parameter）
# 同时给齐 --nodes / --flavor-id / --flavor 时 t_flops 会自动推导为 nodes × flavor_id × flavor
# [HCS] 资源池走顶层 resource_config
pangu training create -f train.yaml \
  --name my-finetune \
  --asset-id <asset_id> \
  --model-id <model_id> \
  --model-type NLP --train-type SFT --model-source pangu \
  --dataset-id <ds_id> --dataset-name ds-train --dataset-version-id v1 \
  --eval-dataset-id <eval_id> --dataset-split-ratio 10 \
  --pool-id <pool_id> --pool-type private --chip-type Snt9B3 \
  --flavor-id 8 --nodes 1 --flavor 313 \
  --plog-level 0

# [HC] 资源池作为 train_flavor 超参注入 task_parameter.parameters
# 必填校验：task_parameter.parameters 中必须有 train_flavor 且 pool_id 非空（不需要 t_flops）
pangu training create -f train.yaml \
  --name my-finetune \
  --asset-id <asset_id> --model-id <model_id> \
  --model-type NLP --train-type SFT --model-source pangu \
  --dataset-id <ds_id> --dataset-name ds-train --dataset-version-id v1 \
  --pool-id <pool_id> --train-flavor "1*ascend-snt9b"

# 量化训练
pangu training create -f quant.yaml --quantization-type QUANTIZATION-W8A8C --output-artifact-name my-quant

# 断点续训
pangu training create -f resume.yaml --checkpoint-id <ckpt_uuid>

# 创建并等待完成（终态 completed / failed / stopped）
pangu training create -f examples/training_create.yaml --wait

# 停止任务（状态为 running / pending 时可用）
pangu training stop <task_id>

# 重试任务（状态为 failed 时可用）
pangu training retry <task_id> --wait

# 批量删除（可传多个 task_id）
pangu training delete <task_id1> <task_id2>

# 查看训练日志（自动获取 execution_id / job_id / worker 节点）
pangu training logs <task_id>
pangu training logs <task_id> --node worker-0

# 查看训练节点信息（用于拿 worker-N 节点名供 logs 使用）
pangu training nodes <task_id>

# 查看训练指标 loss / metric
#   默认 -o chart：终端绘制 loss-epoch 二维曲线 + 每类别 precision/recall 进度条（带百分比）
#   skill/agent 请用 -o json 读取结构化原始 JSON
pangu training metrics <task_id> --model-type NLP              # 可视化（默认）
pangu training metrics <task_id> --model-type NLP -o json      # 原始 JSON（供 skill）

# 查看断点 Checkpoint 列表（分页）
pangu training checkpoints <task_id> --limit 20 --page 1

# 发布模型到资产中心（asset-name / visibility 必填，category 默认 pangu）
pangu training publish <task_id> --asset-name my-model-v1 --visibility current
pangu training publish <task_id> --asset-name q8-v1 --visibility all --category 3rd

# 查看训练任务产生的模型列表（execution_id 自动从任务详情获取）
pangu training models <task_id>
pangu training models <task_id> --model-type NLP --action-type SFT --status published

# AI 科学计算（气象）场景
pangu training models <task_id> --weather-job-type <type> --weather-data-config <cfg>

# 查询时间范围内的资源用量（start-time / end-time 必填）
pangu training usage --start-time 2024-01-01T00:00:00 --end-time 2024-01-31T23:59:59

# 查询指定资源池 / 节点上运行的任务
pangu training running <pool_id>
pangu training running <pool_id> --node-ip 192.168.0.10
```

---

### 数据集管理

> 数据集主键为 `数据集名称 + catalog`（ORIGINAL 原始 / PROCESS 加工 / PUBLISH 发布）。
> 列表走 v2 接口，返回 `id` 字段作为 UUID；删除、发布、加工均按 `name + catalog` 操作。

```bash
# 查询列表（默认 20 条，显示总数与分页提示）
pangu dataset list
pangu dataset list --catalog ORIGINAL --modal TEXT --status ONLINE
pangu dataset list --name keyword --creator admin

# 分页：第 2 页（每页 50 条）
pangu dataset list --limit 50 --page 2

# 拉取全部（适合脚本 / skill 场景）
pangu dataset list --all -o json

# 按创建者过滤 + 仅看我的
pangu dataset list --mine --sort-by create_time --sort-type desc

# 查看详情（按名称+类别）
pangu dataset get <dataset_name> --catalog ORIGINAL

# 按 ID 批量查询
pangu dataset get-by-ids <id1> <id2> <id3>

# 批量软删除（可恢复）
pangu dataset delete <name1> <name2> --catalog ORIGINAL
pangu dataset delete <name> -y              # 跳过确认

# 彻底清除（不可恢复，可同时删除 OBS 源文件）
pangu dataset purge <name> --catalog ORIGINAL
pangu dataset purge <name> --delete-obs -y

# 从 OBS 导入数据（name / obs-path / content-type 必填；obs-path 不含 obs:// 前缀，传入也会自动剥离）
pangu dataset import \
  --name my-dataset \
  --obs-path my-bucket/data/ \
  --content-type PRE_TRAINED_TEXT \
  --file-format JSONL

# 图像类 content_type 与 file_format 固定关联，未传会自动补齐：
#   IMAGE_OBJECT_DETECTION       → PASCAL
#   IMAGE_CLASSIFICATION         → IMAGE_TXT
#   IMAGE_ANOMALY_DETECTION      → IMAGE_TXT
#   IMAGE_SEMANTIC_SEGMENTATION  → IMAGE_PNG
#   IMAGE_INSTANCE_SEGMENTATION  → IMAGE_XML
pangu dataset import --name cls --obs-path bucket/img/ --content-type IMAGE_CLASSIFICATION

# 用 YAML 配置导入并等待完成
pangu dataset import -f examples/dataset_import.yaml --wait

# 发布单个数据集（命令行；会自动按名称查询 dataset_id 并补入请求体）
pangu dataset publish \
  --publish-name my-pub-v1 \
  --source-name my-dataset \
  --source-catalog ORIGINAL \
  --file-content-type SINGLE_QA

# 合并发布多个数据集（--source-name 可多次传入，共用同一 --source-catalog）
pangu dataset publish \
  --publish-name merged-v1 \
  --source-name ds-a --source-name ds-b --source-name ds-c \
  --source-catalog ORIGINAL \
  --file-content-type SINGLE_QA

# 发布数据集（YAML 混合，配置文件覆盖命令行默认值；YAML 中可整体指定 datasets 数组）
pangu dataset publish --publish-name v1 --source-name ds --file-content-type SINGLE_QA -f publish.yaml

# 数据加工（task_operators 字段较多，必须走 YAML）
pangu dataset process --source-name my-dataset -f examples/dataset_process.yaml

# 查询可用算子（嵌套结构：一级分类 → 二级分类 → 算子）
pangu dataset operators
pangu dataset operators --catalog SYS --modal TEXT --category DL

# 数据血缘（按来源 OBS 路径查询）
pangu dataset lineage obs://my-bucket/raw/ --limit 100
```

---

## 输出格式

所有查询命令支持 `-o` / `--output` 参数：

```bash
pangu workspace list -o table   # 默认，彩色表格
pangu workspace list -o json    # JSON（适合脚本解析）
pangu workspace list -o yaml    # YAML
pangu workspace list -o id      # 仅输出 ID（适合管道操作）
```

### 管道示例

```bash
# 获取所有工作空间 ID
pangu workspace list -o id

# 获取运行中服务的 ID 列表
pangu service list --status running -o id
```

---

## 工作空间参数

所有涉及工作空间的命令均支持 `-w` / `--workspace` 参数覆盖默认工作空间：

```bash
pangu service list -w ws-other-id
pangu training create -f job.yaml -w ws-other-id
```

---

## 配置项完整说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `endpoint` | — | 平台 API 地址 |
| `iam_endpoint` | — | IAM 认证地址 |
| `auth_mode` | `token` | 认证模式：`token` \| `apikey` |
| `username` | — | 用户名（token 模式） |
| `domain_name` | — | 租户名（token 模式） |
| `project_name` | — | 项目名称（token 模式） |
| `project_id` | — | 项目 ID |
| `default_workspace_id` | — | 默认工作空间 ID |
| `api_key` | — | API Key（apikey 模式） |
| `password` | — | 登录密码（可选，明文存储） |
| `env_type` | `HCS` | 环境类型：`HCS` \| `HC` |
| `ssl_verify` | `true` | 是否验证 SSL 证书 |
| `timeout` | `60` | HTTP 请求超时秒数 |
| `use_system_proxy` | `true` | 是否读取系统代理设置 |
| `proxy` | — | 显式指定代理地址，如 `http://127.0.0.1:7890` |

## 配置文件位置

| 文件 | 说明 |
|------|------|
| `~/.pangu/config.yaml` | 主配置文件 |
| `~/.pangu/token_cache.yaml` | Token 缓存（自动管理） |
