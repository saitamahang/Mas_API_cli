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
- `--page-size` controls display only. It does not expand backend search scope. Keep it between 1 and 50; use `--limit 1000` for backend search scope.
- Long candidate lists are paged. Never assume output is complete when `has_more: true`; use `pangu-agent candidates --run-id <run_id> --kind <kind> --page <n> --page-size 20 --json` or add a name filter.
- If a command returns `invalid_page_size`, rerun with `--page-size 20` or `--page-size 50`. Do not invent a larger `--page-size`.
- Every submit requires validate first.
- If validate succeeds and a YAML file changes afterward, submit will fail; rerun validate.
- Training submit, model publish, and deployment submit require explicit user approval. Never run an `approve` command or pass `--confirm` until the user clearly approves the shown summary.
- Do not edit generated training YAML for hyperparameter changes. Use `train params` and `train validate --param` instead.
- Training submit reuses validate-time hyperparameter overrides. To change batch size or any other hyperparameter, rerun validate first.
- Model, dataset, pool, and cards form one atomic training context. If any of them changes, rerun `train scaffold`, then rerun `train params -> validate -> approve -> submit`.
- Training datasets must be `catalog=PUBLISH` and `status=ONLINE`. If dataset publish was just submitted, wait for publish completion before training.
- Never delete old templates. `pangu-agent` creates unique artifacts under `~/.pangu/agent_runs/`.
- Clean expired local run state with `pangu-agent gc --max-age-hours 24` when old run IDs pile up.
- If a command returns `ok: false`, follow its `next_action`; do not guess a replacement command.

## Dataset Workflow

Use this when the user needs to find, import, or publish training data.

### List Training Datasets

```bash
pangu-agent dataset list --scenario cv_image_classification --catalog PUBLISH --limit 1000 --page-size 20 --json
```

This lists only ready training datasets for the scenario. If no `PUBLISH`/`ONLINE` dataset exists, prepare and publish data first.
If `has_more: true`, page through results or filter by name:

```bash
pangu-agent candidates --run-id <run_id> --kind datasets --page 2 --page-size 20 --json
pangu-agent dataset list --scenario cv_image_classification --catalog PUBLISH --name <keyword> --limit 1000 --page-size 20 --json
```

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
  --limit 1000 \
  --page-size 20 \
  --json

pangu-agent dataset publish-validate \
  --run-id <run_id> \
  --publish-name <publish_name> \
  --source <index> \
  --train-proportion 0.8

pangu-agent dataset publish-submit --run-id <run_id> --wait
```

For CV image scenarios, use `--train-proportion` unless the command output says otherwise.
If `publish-prepare` returns `has_more: true`, use `pangu-agent candidates --run-id <run_id> --kind sources --page <n> --page-size 20 --json`.
If `publish-submit` was run without `--wait`, run `pangu-agent dataset publish-wait --run-id <run_id> --json` before training. Do not continue to `train plan` until the published dataset is reported ready.

## Training Workflow

Training follows exactly this state machine:

```text
doctor -> scenarios -> train plan -> user chooses indexes -> scaffold -> params -> validate -> user approves -> approve -> submit
```

### Plan

```bash
pangu-agent train plan --scenario cv_image_classification --limit 1000 --page-size 20 --json
```

Show the returned `models`, `datasets`, and `pools` to the user. Ask the user to choose indexes and provide:

- `task_name`
- `cards` (`1`, `2`, `4`, or `8`)
- optional `batch_size` (default comes from scenario; normally `1`)
- optional training hyperparameter overrides

If any `candidate_pages.<kind>.has_more` is true, fetch more compact pages before asking the user to choose:

```bash
pangu-agent candidates --run-id <run_id> --kind datasets --page 2 --page-size 20 --json
```

Use `--dataset-name <keyword>` on `train plan` when the user provides a dataset name hint.
If the desired existing dataset is not returned, do not select it by hand; it is either not `PUBLISH`, not `ONLINE`, not the scenario content type, or outside the current filters.

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

Do not edit the generated YAML unless the user explicitly asks. Use validate-time parameter overrides instead of editing YAML for training hyperparameters.
The generated YAML is bound to the selected model, dataset, pool, and cards. To change any of those choices, rerun `train scaffold` with the new indexes and repeat the downstream steps.

### Params

If the user wants to inspect or change training hyperparameters, list the real parameters from the generated YAML:

```bash
pangu-agent train params --run-id <run_id> --json
```

Use only parameter names or indexes returned by `train params`. Prefer indexes when passing overrides. Do not invent parameter names. Do not override parameters marked `editable: false`.

### Validate

```bash
pangu-agent train validate --run-id <run_id> --batch-size 1
```

For extra hyperparameter overrides, pass them during validate only:

```bash
pangu-agent train validate \
  --run-id <run_id> \
  --batch-size 1 \
  --param <param_index>=<json_value> \
  --param <param_name>=<json_value>
```

Only continue if `ok: true`.
If validate returns `training_param_not_found`, follow `next_action`: rerun `train params` for user-supplied `--param` mistakes, or stop and ask for scenario parameter mapping when batch size cannot be resolved.
If validate returns `training_param_index_not_found`, `protected_training_param`, or `duplicate_training_param_override`, rerun `train params` and ask the user to choose valid editable parameters.
If validate returns `training_context_mismatch`, rerun `train scaffold`; do not patch the YAML or state by hand.
Show `approval_summary` to the user and ask whether to submit the training task. Do not continue without explicit approval.

### Approve

```bash
pangu-agent train approve --run-id <run_id> --confirm submit-training
```

Only run this after the user approves the exact `approval_summary` returned by validate.

### Submit

```bash
pangu-agent train submit --run-id <run_id>
```

Submit reuses the hyperparameter overrides recorded by validate. Do not pass new hyperparameters at submit time. If the user wants a different batch size or any other hyperparameter, rerun validate with the new values, then ask for approval again.

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
  --visibility current \
  --confirm publish-model
```

Only pass `--confirm publish-model` after the user explicitly agrees to publish the model asset.

Resolve outputs for deployment with:

```bash
pangu-agent train published-assets --task-id <task_id> --json
```

## Deployment Workflow

Deployment follows this state machine:

```text
deploy plan -> user chooses option/pool -> scaffold -> validate -> user approves -> approve -> submit
```

### Plan

```bash
pangu-agent deploy plan --asset-id <asset_id> --page-size 20 --json
```

Show returned `deploy_options` and `pools` to the user. Do not hardcode chip types such as `D310P`; use the returned options.
If `candidate_pages.pools.has_more` is true, page through pools with `pangu-agent candidates --run-id <run_id> --kind pools --page <n> --page-size 20 --json`.

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
Show `approval_summary` to the user and ask whether to deploy the inference service. Do not continue without explicit approval.

### Approve

```bash
pangu-agent deploy approve --run-id <run_id> --confirm deploy-service
```

Only run this after the user approves the exact `approval_summary` returned by validate.

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
