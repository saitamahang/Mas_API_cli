#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  install-pangu-agent.sh <wheel> [options]

Options:
  --adapter <name>              Monitor adapter name. Default: codeagent
  --adapter-package <pkg>       Pip package for adapter SDK. Can be repeated.
  --plugin-package <pkg>        Pip package for an agent plugin. Can be repeated.
  --skip-config                 Skip interactive pangu config init.
  --skip-doctor                 Skip pangu-agent doctor check.
  --no-force-skill              Do not overwrite existing skill.
  -h, --help                    Show help.

Example:
  ./scripts/install-pangu-agent.sh ./dist/pangu_cli-0.2.0-py3-none-any.whl \
    --adapter codeagent \
    --adapter-package codeagent-sdk
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

WHEEL=""
ADAPTER="codeagent"
SKIP_CONFIG=0
SKIP_DOCTOR=0
FORCE_SKILL=1
ADAPTER_PACKAGES=()
PLUGIN_PACKAGES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --adapter)
      ADAPTER="${2:?--adapter requires a value}"
      shift 2
      ;;
    --adapter-package)
      ADAPTER_PACKAGES+=("${2:?--adapter-package requires a value}")
      shift 2
      ;;
    --plugin-package)
      PLUGIN_PACKAGES+=("${2:?--plugin-package requires a value}")
      shift 2
      ;;
    --skip-config)
      SKIP_CONFIG=1
      shift
      ;;
    --skip-doctor)
      SKIP_DOCTOR=1
      shift
      ;;
    --no-force-skill)
      FORCE_SKILL=0
      shift
      ;;
    *)
      if [[ -z "$WHEEL" ]]; then
        WHEEL="$1"
        shift
      else
        echo "Unknown argument: $1" >&2
        usage
        exit 2
      fi
      ;;
  esac
done

if [[ -z "$WHEEL" ]]; then
  echo "Missing wheel path." >&2
  usage
  exit 2
fi

python -m pip install --upgrade "$WHEEL"

for package in "${PLUGIN_PACKAGES[@]}"; do
  python -m pip install --upgrade "$package"
done

for package in "${ADAPTER_PACKAGES[@]}"; do
  python -m pip install --upgrade "$package"
done

INIT_ARGS=(init --install-skill --adapter "$ADAPTER")
if [[ "$FORCE_SKILL" -eq 1 ]]; then
  INIT_ARGS+=(--force-skill)
else
  INIT_ARGS+=(--no-force-skill)
fi
if [[ "$SKIP_CONFIG" -eq 1 ]]; then
  INIT_ARGS+=(--skip-config)
fi
if [[ "$SKIP_DOCTOR" -eq 1 ]]; then
  INIT_ARGS+=(--skip-doctor)
fi

if command -v pangu-agent >/dev/null 2>&1; then
  pangu-agent "${INIT_ARGS[@]}"
else
  python -m pangu.agent_main "${INIT_ARGS[@]}"
fi
