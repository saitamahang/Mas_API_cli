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

```bash
# 查看详情
pangu training get <task_id>

# 创建任务（YAML 配置，推荐）
pangu training create -f examples/training_create.yaml

# 创建任务（命令行参数，必填项较多）
pangu training create \
  --name my-finetune \
  --asset-id <asset_id> \
  --model-id <model_id> \
  --model-type NLP \
  --train-type SFT \
  --model-source pangu \
  --t-flops 313 \
  --pool-id <pool_id> \
  --nodes 1

# 创建并等待完成
pangu training create -f examples/training_create.yaml --wait

# 停止任务（状态为 running/pending 时可用）
pangu training stop <task_id>

# 重试任务（状态为 failed 时可用）
pangu training retry <task_id>
pangu training retry <task_id> --wait

# 批量删除（可传多个 task_id）
pangu training delete <task_id1> <task_id2>

# 查看训练日志（自动获取 execution_id 和 job_id）
pangu training logs <task_id>
pangu training logs <task_id> --node worker-0

# 查看训练节点信息
pangu training nodes <task_id>

# 查看训练指标
pangu training metrics <task_id> --model-type NLP

# 查看断点 Checkpoint 列表
pangu training checkpoints <task_id>

# 发布模型到资产中心（asset-name 和 visibility 必填）
pangu training publish <task_id> --asset-name my-model-v1 --visibility current

# 查看训练任务产生的模型列表（execution_id 必填，自动从任务详情获取）
pangu training models <task_id>
pangu training models <task_id> --model-type NLP --action-type SFT

# 获取模型详情（创建训练任务前用于查询 task_parameter 模板，3.13.11）
pangu training model-detail \
  --model-id <model_id> \
  --model-type NLP \
  --train-type SFT \
  --model-source pangu

# 查询时间范围内的资源用量（start-time 和 end-time 必填）
pangu training usage --start-time 2024-01-01T00:00:00 --end-time 2024-01-31T23:59:59

# 查询指定资源池上运行的任务（pool_id 必填）
pangu training running <pool_id>
```

---

### 数据集管理

```bash
# 查询列表
pangu dataset list
pangu dataset list --type text --status ready

# 查看详情
pangu dataset get <dataset_id>

# 删除
pangu dataset delete <dataset_id>
pangu dataset purge <dataset_id>   # 彻底清除，不可恢复

# 从 OBS 导入数据
pangu dataset import <dataset_id> --obs-path obs://my-bucket/data/
pangu dataset import <dataset_id> -f examples/dataset_import.yaml --wait

# 发布版本
pangu dataset publish <dataset_id> --version-name v1.0

# 查询已发布版本
pangu dataset publish-list <dataset_id>

# 删除已发布版本
pangu dataset publish-delete <dataset_id> <annotation_id>

# 数据处理
pangu dataset process <dataset_id> --operator text_clean
pangu dataset process <dataset_id> -f examples/dataset_process.yaml --wait

# 查询可用算子
pangu dataset operators

# 数据血缘
pangu dataset lineage <dataset_id>
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
