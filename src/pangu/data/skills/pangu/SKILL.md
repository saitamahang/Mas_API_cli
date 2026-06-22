---
name: pangu-training
description: Pangu platform operations: CV training tasks and edge service deployment
allowed-tools: Bash(pangu:*)
---

# Pangu Platform Operations

## Global Rules

- **NEVER** hardcode model/dataset/pool IDs. All IDs MUST come from query results.
- **ALWAYS** use `--source Preset` for training tasks.
- User **MUST** select model, dataset, pool from filtered query results.
- Scaffold auto-fills all technical fields (`dataset_id`, `obs_url`, `flavor_id`, `model_name`, etc.). Only `task_name` and `batch_size` come from user input.
- Token expired? Run `pangu auth login` first.

---

## Training Workflow

### Step 1: Clean old template

```bash
rm -f train_template.yaml
```

### Step 2: Query pretrained models (MUST be first)

```bash
pangu model list --type CV --sub-type IC --source Preset --simple --output json
```

- `--type`: `CV` (Computer Vision), `NLP`, `AUDIO`
- `--sub-type`: `IC` (Image Classification), `OD` (Object Detection), `TC` (Text Classification)
- **ALWAYS** use `--source Preset` — training MUST use preset models, never custom models.
- Present filtered results to user for selection.

### Step 3: Query PUBLISH catalog datasets

```bash
pangu dataset list --catalog PUBLISH --modal IMAGE --content-type IMAGE_CLASSIFICATION --output json
```

- `--modal`/`--content-type` must match the selected model type. Use `pangu dataset list --help` if unsure.
- Present filtered results to user for selection.

### Step 4: Query resource pools

```bash
pangu pool list --job-type train --use-type private --output json
```

- If multiple pools returned, present to user for selection.
- If only one pool returned, use it automatically.

### Step 5: Generate training template

```bash
pangu training scaffold \
  --model-id <selected_model_id> \
  --model-type <selected_model_type> \
  --train-type SFT \
  --model-source SYSTEM \
  --dataset-name <selected_dataset_name> \
  --dataset-catalog PUBLISH \
  --pool-id <selected_pool_id> \
  --chip-type <selected_chip_type> \
  --cards <selected_card_count> \
  --out train_template.yaml
```

**Parameters:**

| Parameter | Source | Description |
|-----------|--------|-------------|
| `--model-id` | User selection (Step 2) | Model UUID |
| `--model-type` | User selection (Step 2) | e.g. `CV`, `NLP` |
| `--train-type` | Fixed | `SFT` for fine-tuning |
| `--model-source` | Fixed | Always `SYSTEM` |
| `--dataset-name` | User selection (Step 3) | Dataset **name** (NOT `dataset_id`) |
| `--dataset-catalog` | Fixed | `PUBLISH` |
| `--pool-id` | User selection (Step 4) | Pool UUID |
| `--chip-type` | User selection (Step 4) | e.g. `D910B3`, `D910A` |
| `--cards` | User choice (1/2/4/8) | Cards per node. `2` is RECOMMENDED |

**What Scaffold Fills Internally:**

- **Dataset**: `dataset_id`, `dataset_name`, `dataset_version_id`, `obs_url`
- **Pool**: `flavor_id` (from `--cards`), `chip_type`, `pool_id`, `t_flops`, `node_count`
- **Model**: `model_name`, `asset_id`, `workflow_info.parameters`

**IMPORTANT — `obs_url` Path:**

Resulting `obs_url` MUST start with `/`.  
- **Correct**: `/cv-test/dataset/.../data.manifest`
- **Wrong**: `cv-test/dataset/.../data.manifest`

### Step 6: Ask user for task_name and batch_size, then write to template

**`task_name`**: max 64 chars, must be unique. Suggest format: `ImageClassificationTrain_YYYYMMDD_001`

**`batch_size`**: Recommend `1` for most tasks (especially large datasets). Typical range: `1-32`.

Write ONLY these two values to `train_template.yaml`. NEVER manually edit other fields.

### Step 7: Submit

```bash
pangu training create -f train_template.yaml
```

### Step 8: Check training status and publish model (after task completes)

After task submission, check status with `pangu training get <task_id>`.  
Status values include: `已创建`, `运行中`, `已完成`, `失败`, `已停止`.

**When status is `已完成` (success):**

- Notify user training has completed.
- Ask user: "是否将训练产物发布为模型资产？(y/n)"
- If user agrees, collect:
  - `asset_name`: Suggest format `Model_<task-id>_<YYYYMMDD>`
  - `visibility`: Recommend `current` (本空间), alternative `all` (全空间) or specific `<workspace_id>`
  - `description`: Optional model description

```bash
pangu training publish <task_id> \
  --asset-name <asset_name> \
  --visibility current \
  --description <description>
```

- Output includes `model_id`, use it for subsequent edge service deployment.

**When task is manually queried later:**

- Follow the same flow: check status → if completed → ask user → publish if agreed.
- If user declines publishing, training workflow ends.

---

## Edge Service Deployment Workflow

### Step 1: Clean old templates

```bash
rm -f deploy_edge_*.yaml
```

**IMPORTANT**: MUST delete old templates before regenerating to avoid stale ELB IDs or specs.

### Step 2: Get model resource options (MUST be second)

```bash
pangu model get <asset_id> --show-resources -o json
```

Returns `deploy_options` with `chip_types`, `arch`, `spec`, and recommended `pool_cmd`.

### Step 3: Ask user to select deploy option

Present `deploy_options` to user. Ask user to choose:

- **Architecture**: `ARM` or `X86`
- **Deployment type**: `EDGE-DEPLOY` or `ONLINE-DEPLOY`
- Use the selected option's `pool_cmd` for Step 4.

### Step 4: Query resource pools

```bash
pangu pool list --chip-type <chip_from_selection> --arch <arch_from_selection> --edge
```

- If multiple pools returned, present to user for selection.

### Step 5: Generate scaffold template

```bash
pangu service scaffold \
  --asset-id <asset_id> \
  --infer-type edge \
  --pool-id <selected_pool_id> \
  --edge-access-mode ELB \
  --name <service_name> \
  -o deploy_edge_v1.yaml
```

**Parameters:**

| Parameter | Source | Description |
|-----------|--------|-------------|
| `--asset-id` | User provided | Published model asset UUID |
| `--infer-type` | Fixed | `edge` |
| `--pool-id` | User selection (Step 3) | Edge pool UUID |
| `--edge-access-mode` | User choice | `ELB` or `NODE`. `ELB` auto-fills `elb_id` |
| `--name` | User provided | Unique service name |

**What Scaffold Fills:**

- `elb_id` (when `--edge-access-mode ELB`)
- `custom_spec` (cpu, memory, ascend)
- `user_env` (`MOUNT_LOCATION`, etc.)
- `asset_tag`, `chip_type`, `arch`

**IMPORTANT**: MUST delete old templates before regenerating to avoid stale ELB IDs or specs.

### Step 5: Deploy

```bash
pangu service deploy --config deploy_edge_v1.yaml
```

### Step 6: Verify deployment

```bash
pangu service get <service_id>
```

Status lifecycle: `init` → `deploying` → `running` (or `failed`).  
Poll every 20-30 seconds. Wait time: 2-5 minutes.

---

## Task & Service Management

### Training Task

```bash
pangu training get <task_id>
pangu training logs <task_id> --execution-id <execution_id> --job-id <job_id>
pangu training stop <task_id>
pangu training delete <task_id>
```

### Edge Service

```bash
pangu service get <service_id>
pangu service list --infer-type edge
pangu service start <service_id>
echo y | pangu service delete <service_id>  # Pipe bypasses interactive confirmation
```

---

## Common Errors & Solutions

### Error: No models found / Invalid filters

- **Error**: No models found matching the specified criteria
- **Cause**: Wrong `--type` or `--sub-type` values
- **Fix**: Use `pangu model list --help` to check valid filters. Common: `--type CV --sub-type IC` (image classification), `--type CV --sub-type OD` (object detection), `--type NLP --sub-type TC` (text classification).

### Error: Wrong model used for task

- **Error**: `训练失败: 模型类型不匹配或模型不支持此训练任务`
- **Cause**: Using custom model instead of Preset model, or wrong model type
- **Fix**: Always use `--source Preset` in query and `--model-source SYSTEM` in scaffold.

### Error: Dataset not found in PUBLISH catalog

- **Error**: `APIError: [404] dataset [...] not found in catalog [PUBLISH]`
- **Cause**: Used `ORIGINAL` catalog name instead of `PUBLISH` catalog name
- **Fix**: Use the `PUBLISH` catalog dataset name from `pangu dataset list --catalog PUBLISH` results.

### Error: Missing scaffold parameters

- **Error**: `env_type=HC: task_parameter.parameters 中缺少 train_flavor 或其 pool_id 为空`
- **Cause**: Missing `--pool-id` or invalid pool
- **Fix**: Ensure `--pool-id` is from a valid, available pool. Query pools first.

### Error: Incorrect obs_url path

- **Context**: `obs_url` in template missing leading `/`
- **Fix**: Ensure `obs_url` starts with `/`. Correct transformation: `obs://path/to/file` → `/path/to/file`

### Error: Resource chip mismatch (Edge deployment)

- **Error**: `APIError: [400] MAStudio.00310136: The number of resource infos for filtering model assets is incorrect`
- **Cause**: Using training chip (`D910B3`) for edge deployment
- **Fix**: Use `--show-resources` to determine correct chip. Edge MUST use `D310P`.

### Error: Token expired

- **Error**: `ValueError: Token 未获取或已过期`
- **Fix**: Run `pangu auth login`

### Error: Task/Service name already exists

- **Error**: `APIError: [409] The name already exists: ...`
- **Fix**: Use unique name with timestamp or version number.

---

## Pre-Submit Checklist

### Global

- [ ] Token valid (`pangu auth login` if expired)
- [ ] No hardcoded IDs — all from query results

### Training

- [ ] Models queried with `--type`, `--sub-type`, `--source Preset`
- [ ] User selected model from results
- [ ] Dataset queried with `--catalog PUBLISH` + correct filters
- [ ] User selected dataset name from results
- [ ] Pool queried before template generation
- [ ] User selected pool and card count (1/2/4/8)
- [ ] `--dataset-name` uses name (NOT id), `--pool-id` uses UUID, `--train-type SFT`, `--model-source SYSTEM`
- [ ] `obs_url` starts with `/`
- [ ] Task status checked (`已完成` = completed, `失败` = failed, `运行中` = running)
- [ ] If completed: user notified, asked if they want to publish
- [ ] If publishing: `--asset-name` provided, `--visibility current` used by default

### Edge Service

- [ ] `--show-resources` output obtained
- [ ] User selected arch/chip from `deploy_options`
- [ ] Edge pools queried with correct `pool_cmd`
- [ ] Old templates deleted before scaffold
- [ ] `--edge-access-mode ELB` specified in scaffold
- [ ] Service name is unique

---

## Key Commands Reference

```bash
# Auth
pangu auth login

# Model (training)
pangu model list --type CV --sub-type IC --source Preset --simple --output json
pangu model list --help

# Model (edge)
pangu model get <asset_id> --show-resources -o json

# Dataset
pangu dataset list --catalog PUBLISH --modal IMAGE --content-type IMAGE_CLASSIFICATION --output json
pangu dataset list --help

# Resource Pool (training)
pangu pool list --job-type train --use-type private --output json

# Resource Pool (edge)
pangu pool list --chip-type D310P --arch ARM --edge

# Training Scaffold
pangu training scaffold \
  --model-id <id> --model-type CV --train-type SFT --model-source SYSTEM \
  --dataset-name "<name>" --dataset-catalog PUBLISH \
  --pool-id <pool> --chip-type <chip> --cards 2 \
  --out train_template.yaml

# Edge Service Scaffold
pangu service scaffold \
  --asset-id <id> --infer-type edge --pool-id <pool> \
  --edge-access-mode ELB --name <name> -o deploy_edge_v1.yaml

# Training Submit, Publish & Manage
pangu training create -f train_template.yaml
pangu training get <task_id>
pangu training logs <task_id> --execution-id <id> --job-id <id>
pangu training publish <task_id> --asset-name <name> --visibility current
pangu training stop <task_id>
pangu training delete <task_id>

# Edge Service Deploy & Manage
pangu service deploy --config deploy_edge_v1.yaml
pangu service get <service_id>
pangu service list --infer-type edge
pangu service start <service_id>
```
