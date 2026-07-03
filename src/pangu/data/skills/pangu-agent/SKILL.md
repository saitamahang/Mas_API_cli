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
- Before starting a workflow, identify the user's goal and pass it to the entry command with `--goal`.
- Supported goals are `dataset_ready`, `training_submitted`, `training_completed`, `model_published`, `deployment_submitted`, and `service_running`.
- If a command returns `terminal: true` or `next_action: stop`, stop the workflow. Do not continue to publish or deploy unless the user's original goal requires it.
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

Goal defaults are conservative: dataset workflows default to `dataset_ready`, training workflows default to `training_submitted`, and deployment workflows default to `deployment_submitted`. Use farther goals only when the user asks for them.
If the user expands the goal later, pass the new `--goal` on the next status/publish command that accepts it so the saved run state is updated.
When `next_action` starts a new run, such as `train.plan` after dataset publish or `deploy.plan` after model resolution, pass the same `goal` value returned by the previous command.

## Async Monitor Rules

Long training and deployment waits should not be polled inside the main agent session. For goals beyond submitted, prefer atomic submit with `--session-id <session_id>` so `train submit` / `deploy submit` creates the detached monitor before returning. After `train submit`, `deploy submit`, `train status`, or `deploy status`, if the response has `next_action: monitor.add` or `monitor_required: true`, create a detached monitor and then stop the main session.

Use the configured monitor adapter and source session:

- `pangu config set monitor_adapter codeagent` (default)
- `PANGU_MONITOR_ADAPTER` for temporary override
- `PANGU_MONITOR_SESSION_ID`

Do not guess the adapter. The default adapter name comes from pangu config and defaults to `codeagent`. If the session id is not available, ask the user to configure it or pass `--session-id`. Do not invent a session id.

Detached monitor creation:

```bash
pangu-agent monitor add \
  --run-id <run_id> \
  --session-id <session_id> \
  --detach \
  --json
```

The monitor reuses `pangu-agent train status` / `pangu-agent deploy status` in a background process and sends a user-like message back to the source session when the task reaches a terminal state. If submit/status returns both a status command and `monitor_add_template`, follow `next_action`; do not poll status commands in the main session when `next_action` is `monitor.add`. Never run raw `pangu service get` or raw `pangu training get` loops. It must not auto-approve, auto-publish, or auto-deploy.

## Dataset Workflow

Use this when the user needs to find, import, or publish training data.

### List Training Datasets

```bash
pangu-agent dataset list --scenario cv_image_classification --catalog PUBLISH --goal dataset_ready --limit 1000 --page-size 20 --json
```

This lists only ready training datasets for the scenario. If no `PUBLISH`/`ONLINE` dataset exists, prepare and publish data first.
If `has_more: true`, page through results or filter by name:

```bash
pangu-agent candidates --run-id <run_id> --kind datasets --page 2 --page-size 20 --json
pangu-agent dataset list --scenario cv_image_classification --catalog PUBLISH --name <keyword> --goal dataset_ready --limit 1000 --page-size 20 --json
```

### Import OBS Data

```bash
pangu-agent dataset import-validate \
  --scenario cv_image_classification \
  --name <dataset_name> \
  --obs-path <bucket/path/> \
  --goal dataset_ready

pangu-agent dataset import-submit --run-id <run_id> --wait
```

Do not pass `content_type` or `file_format`; the scenario profile supplies them.

### Publish Dataset

```bash
pangu-agent dataset publish-prepare \
  --scenario cv_image_classification \
  --source-catalog ORIGINAL \
  --goal dataset_ready \
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
If `publish-submit` was run without `--wait`, run `pangu-agent dataset publish-wait --run-id <run_id> --json` before training. Publish wait uses the same readiness signal as `pangu dataset get <publish_name> -c PUBLISH`: the published dataset must be `ONLINE`. Do not continue to `train plan` until the published dataset is reported ready.

## Training Workflow

Training follows exactly this state machine:

```text
doctor -> scenarios -> train plan -> user chooses indexes -> scaffold -> params -> validate -> user approves -> approve -> submit
```

### Plan

```bash
pangu-agent train plan --scenario cv_image_classification --goal training_submitted --limit 1000 --page-size 20 --json
```

Use `--goal training_completed` only when the user wants to wait until the training task finishes. Use `--goal model_published` or `--goal service_running` only when the user explicitly asks to continue past training.

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
After scaffold, always run `train params` and show the full returned parameter list before validate. Do not skip this step even when the user does not plan to change hyperparameters.

### Params

List the real parameters from the generated YAML:

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
Do not run validate until `train params` has succeeded for the current generated YAML. If validate returns `training_params_not_listed` or `training_params_stale`, run `train params` again and show the full returned parameter list.
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
pangu-agent train submit --run-id <run_id> --session-id <session_id>
```

Submit reuses the hyperparameter overrides recorded by validate. Do not pass new hyperparameters at submit time. If the user wants a different batch size or any other hyperparameter, rerun validate with the new values, then ask for approval again.

After submit, stop if the response has `terminal: true`. If submit returns `monitor_created: true`, stop the main session immediately. If `monitor_created` is false and the response has `next_action: monitor.add` or `monitor_required: true`, do not poll in the main session. Use the returned `monitor_add_template` or `monitor.command_template` and create a detached monitor:

```bash
pangu-agent monitor add --run-id <run_id> --session-id <session_id> --detach --json
```

After the monitor is created successfully, stop the main session. When the background monitor reports completion back into this session, continue from the returned `next_action`.

### Publish Training Output

When a task is completed and the user wants to publish:

```bash
pangu-agent train publish \
  --run-id <run_id> \
  --task-id <task_id> \
  --asset-name <asset_name> \
  --visibility current \
  --confirm publish-model
```

Only pass `--confirm publish-model` after the user explicitly agrees to publish the model asset.

Resolve outputs for deployment with:

```bash
pangu-agent train published-assets --run-id <run_id> --task-id <task_id> --json
```

Do not pass `publish_result.model_id` to deployment. Publishing returns a training model ID, while deployment requires a model asset ID. Use `published_asset_id`, `published_asset.asset_id`, or the returned `deploy_plan_command`. If asset resolution is not ready yet, rerun `train published-assets`; do not guess the asset ID.

## Deployment Workflow

Deployment follows this state machine:

```text
deploy plan -> user chooses option/pool -> scaffold -> validate -> user approves -> approve -> submit
```

### Plan

```bash
pangu-agent deploy plan --asset-id <asset_id> --goal deployment_submitted --page-size 20 --json
```

`<asset_id>` must come from `published_asset_id` / `published_asset.asset_id` / `deploy_plan_command`, or from an existing model asset returned by `pangu-agent` candidates. Never use a training `model_id` as `--asset-id`.

Use `--goal service_running` only when the user wants to wait until the service is running.

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

### Submit and Async Monitor

```bash
pangu-agent deploy submit --run-id <run_id> --session-id <session_id>
```

After submit, stop if the response has `terminal: true`. If submit returns `monitor_created: true`, stop the main session immediately. If `monitor_created` is false and the response has `next_action: monitor.add` or `monitor_required: true`, create a detached monitor instead of polling in the main session. When the monitor reports `running` or a failure state back into this session, continue according to the returned message and existing workflow rules.

## Supported Initial Scenarios

- `cv_image_classification`
- `cv_object_detection`
- `cv_semantic_segmentation`
- `cv_anomaly_detection`
- `cv_rotated_object_detection`
- `cv_object_tracking`

Add a new scenario profile in code before using any scenario not listed by `pangu-agent scenarios --json`.
