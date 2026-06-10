---
name: pangu-agent
description: Agent-safe Pangu workflows for dataset preparation, CV training, model publishing, and edge/online deployment. Use this instead of raw pangu commands when an agent operates the Pangu platform.
allowed-tools: Bash(pangu-agent:*)
---

# Pangu Agent-Safe Workflow

Use `pangu-agent` only. Do not call raw `pangu model`, `pangu dataset`, `pangu pool`, `pangu training`, or `pangu service` commands from this skill.

The agent is not allowed to invent CLI flags or IDs. It must use scenario names, run IDs, and indexed candidates returned by `pangu-agent`.

## Global Rules

- Start every session with `pangu-agent doctor --json`.
- List scenarios with `pangu-agent scenarios --json`.
- If a scenario is unsupported, stop and ask for a scenario profile to be added.
- IDs and names used for model/dataset/pool selection must come from `plan` output.
- Use candidate indexes, not manually typed IDs, whenever a command accepts `--model`, `--dataset`, `--pool`, `--option`, or `--source`.
- Every submit requires validate first.
- If validate succeeds and a YAML file changes afterward, submit will fail; rerun validate.
- If training validate used `--batch-size`, submit must use the same value or omit it. To change batch size, rerun validate first.
- Never delete old templates. `pangu-agent` creates unique artifacts under `~/.pangu/agent_runs/`.
- Clean expired local run state with `pangu-agent gc --max-age-hours 24` when old run IDs pile up.
- If a command returns `ok: false`, follow its `next_action`; do not guess a replacement command.

## Dataset Workflow

Use this when the user needs to find, import, or publish training data.

### List Training Datasets

```bash
pangu-agent dataset list --scenario cv_image_classification --catalog PUBLISH --json
```

If no `PUBLISH` dataset exists, prepare data first.

### Import OBS Data

```bash
pangu-agent dataset import-validate \
  --scenario cv_image_classification \
  --name <dataset_name> \
  --obs-path <bucket/path/>

pangu-agent dataset import-submit --run-id <run_id> --wait
```

Do not pass `content_type` or `file_format`; the scenario profile supplies them.

### Publish Dataset

```bash
pangu-agent dataset publish-prepare \
  --scenario cv_image_classification \
  --source-catalog ORIGINAL \
  --json

pangu-agent dataset publish-validate \
  --run-id <run_id> \
  --publish-name <publish_name> \
  --source <index> \
  --train-proportion 0.8

pangu-agent dataset publish-submit --run-id <run_id>
```

For CV image scenarios, use `--train-proportion` unless the command output says otherwise.

## Training Workflow

Training follows exactly this state machine:

```text
doctor -> scenarios -> train plan -> user chooses indexes -> scaffold -> validate -> submit
```

### Plan

```bash
pangu-agent train plan --scenario cv_image_classification --json
```

Show the returned `models`, `datasets`, and `pools` to the user. Ask the user to choose indexes and provide:

- `task_name`
- `cards` (`1`, `2`, `4`, or `8`)
- optional `batch_size` (default comes from scenario; normally `1`)

### Scaffold

```bash
pangu-agent train scaffold \
  --run-id <run_id> \
  --model <model_index> \
  --dataset <dataset_index> \
  --pool <pool_index> \
  --task-name <task_name> \
  --cards <1|2|4|8>
```

Do not edit the generated YAML unless the user explicitly asks. Use `--batch-size` during validate/submit instead of editing YAML for batch size.

### Validate

```bash
pangu-agent train validate --run-id <run_id> --batch-size 1
```

Only continue if `ok: true`.
If validate returns `training_param_not_found`, stop and ask for the scenario parameter mapping to be updated.

### Submit

```bash
pangu-agent train submit --run-id <run_id> --batch-size 1
```

Use the same `--batch-size` value as validate. If the user wants a different batch size, rerun validate with the new value before submit.

After submit, use:

```bash
pangu-agent train status --task-id <task_id> --json
```

### Publish Training Output

When a task is completed and the user wants to publish:

```bash
pangu-agent train publish \
  --task-id <task_id> \
  --asset-name <asset_name> \
  --visibility current
```

Resolve outputs for deployment with:

```bash
pangu-agent train published-assets --task-id <task_id> --json
```

## Deployment Workflow

Deployment follows this state machine:

```text
deploy plan -> user chooses option/pool -> scaffold -> validate -> submit
```

### Plan

```bash
pangu-agent deploy plan --asset-id <asset_id> --json
```

Show returned `deploy_options` and `pools` to the user. Do not hardcode chip types such as `D310P`; use the returned options.

### Scaffold

```bash
pangu-agent deploy scaffold \
  --run-id <run_id> \
  --option <deploy_option_index> \
  --pool <pool_index> \
  --service-name <service_name> \
  --access-mode ELB
```

### Validate

```bash
pangu-agent deploy validate --run-id <run_id>
```

Only continue if `ok: true`.

### Submit and Poll

```bash
pangu-agent deploy submit --run-id <run_id>
pangu-agent deploy status --service-id <service_id> --json
```

Poll status until `running` or `failed`.

## Supported Initial Scenarios

- `cv_image_classification`
- `cv_object_detection`
- `cv_semantic_segmentation`

Add a new scenario profile in code before using any scenario not listed by `pangu-agent scenarios --json`.
