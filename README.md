# pangu-cli

盘古大模型平台管理 CLI，支持工作空间、模型资产、推理服务、训练任务、数据集等全生命周期管理。

## 安装

```bash
pip install -e .
```

安装后即可使用 `pangu` 命令。

---

## 初始化配置

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
| project_id | 项目 ID | `abc123...` |
| default_workspace_id | 默认工作空间 ID | `ws-xxx` |

配置保存在 `~/.pangu/config.yaml`，可随时用 `pangu config show` 查看。

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

### 单项修改

```bash
pangu config set default_workspace_id ws-new-id
pangu config set timeout 60
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
# 或通过环境变量传入密码（适合 CI/CD）
PANGU_PASSWORD=your_password pangu auth login
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

```bash
pangu pool list
pangu pool list -w <workspace_id>
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

```bash
# 查询列表
pangu training list
pangu training list --status running
pangu training list --name keyword --limit 20

# 查看详情
pangu training get <job_id>

# 创建任务（命令行参数）
pangu training create \
  --name my-finetune \
  --asset-id <asset_id> \
  --asset-type NLP \
  --task-type finetune \
  --pool-id <pool_id> \
  --instances 8

# 创建任务（YAML 配置）
pangu training create -f examples/training_create.yaml

# 创建并等待完成
pangu training create -f examples/training_create.yaml --wait

# 停止 / 重试 / 删除
pangu training stop <job_id>
pangu training retry <job_id>
pangu training delete <job_id>

# 查看日志
pangu training logs <job_id>
pangu training logs <job_id> --step train --lines 200
pangu training node-logs <job_id> <node_id>

# 节点列表
pangu training nodes <job_id>

# 训练指标
pangu training metrics <job_id>
pangu training metrics <job_id> --metric loss

# Checkpoint 列表
pangu training checkpoints <job_id>

# 发布为模型资产
pangu training publish <job_id> --asset-name my-model-v1

# 历史版本
pangu training versions <job_id>

# 资源用量
pangu training usage <job_id>

# 快捷查看运行中任务
pangu training running
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

## 配置文件位置

| 文件 | 说明 |
|------|------|
| `~/.pangu/config.yaml` | 主配置文件 |
| `~/.pangu/token_cache.yaml` | Token 缓存（自动管理） |
