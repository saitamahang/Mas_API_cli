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
pangu pool list --job-type Train --status created
pangu pool list -w <workspace_id>
```

**HC 环境**（需先 `pangu config set env_type HC`）：

```bash
# job-type、chip-type、use-type 为 HC 环境 API 必填项
pangu pool list --job-type train --chip-type D910B3 --use-type private
pangu pool list --job-type infer --chip-type D910B3 --use-type poc
```

---

### 模型资产管理

```bash
# 查询列表
pangu model list
pangu model list --type NLP --category pangu
pangu model list --name "盘古" --limit 10

# 查看详情
pangu model get <asset_id>

# 含部署信息的完整列表
pangu model list-ext

# 导出为 ModelArts Site 格式
pangu model export <asset_id>

# 查询导出任务
pangu model export-tasks <asset_id>
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
| `model_source` | 固定枚举 `pangu / third / pangu-third` |
| `t_flops` | 整数：卡数 × flavor（`pangu pool list` 看 flavor，常见 313 / 280） |
| `task_parameter` | 复杂对象，**必须先调 `pangu training model-detail` 取 `workflow_info.parameters` 作模板**，改写后放入 YAML |

> `task_parameter` 结构因 `model_id + train_type` 组合而异（learning_rate / warmup / batch_size / training_flavor / sfs_* 等几十项），不能凭空写。固定流程：`model-detail` → 改参数 → `create`。

**核心枚举**（按《训练任务管理 API》权威定义）：

| 字段 | 取值 |
|---|---|
| `--model-type` | `NLP` (NLP大模型) · `MM` (多模态) · `CV` · `Predict` (预测) · `AI4Science` (科学计算) |
| `--train-type` | `SFT` (全量微调) · `PRETRAIN` (预训练) · `LORA` (lora) · `DPO` · `RFT` |
| `--model-source` | `pangu` (预置) · `third` (三方) · `pangu-third` (盘古提供的三方) |
| `--visibility` (publish) | `current` (当前空间) · `all` (全部空间) |
| `--category` (publish) | `pangu` · `3rd` · `pangu-poc` · `pangu-iit` · `3rd-pangu` |
| `--action-type` (models) | `PRETRAIN` · `SFT` · `LORA` · `QUANTIZATION` · `DPO` |
| `--status` (models) | `published` · `unpublished` |
| `--plog-level` | `-1`(不开启) · `0`(info) · `1`(debug) · `2`(warning) · `3`(error) |
| task_status | `init` · `wait_created` · `pending` · `running` · `stopping` · `stopped` · `failed` · `completed` |

```bash
# 查看详情
pangu training get <task_id>

# 创建前：先取 task_parameter 模板（3.13.11）
pangu training model-detail \
  --model-id <model_id> \
  --model-type NLP \
  --train-type SFT \
  --model-source pangu -o yaml > task_params.yaml

# 创建任务（必须走 YAML；task_parameter 结构来自 model-detail 的 workflow_info.parameters）
pangu training create -f examples/training_create.yaml

# 创建任务（命令行覆盖 YAML；必填: task_name / asset_id / model_type / train_type / model_source / t_flops / task_parameter）
pangu training create -f examples/training_create.yaml \
  --name my-finetune \
  --asset-id <asset_id> \
  --model-id <model_id> \
  --model-type NLP --train-type SFT --model-source pangu \
  --dataset-id <ds_id> --dataset-name ds-train --dataset-version-id v1 \
  --eval-dataset-id <eval_id> --dataset-split-ratio 10 \
  --pool-id <pool_id> --pool-type private --chip-type Snt9B3 --flavor-id 8 \
  --nodes 1 --flavor 313 --t-flops 313 \
  --plog-level 0

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
pangu training metrics <task_id> --model-type NLP

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
