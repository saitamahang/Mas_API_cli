# -*- coding: utf-8 -*-
"""Render static SVG diagrams for the pangu-agent design document."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from textwrap import wrap


OUT_DIR = Path(__file__).resolve().parent
FONT = (
    "-apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', "
    "Arial, sans-serif"
)


def xml_text(text: str) -> str:
    return escape(text, quote=True)


def wrapped_lines(text: str, width: int = 32) -> list[str]:
    if "<br/>" in text:
        return text.split("<br/>")
    return wrap(text, width=width, break_long_words=False, break_on_hyphens=False) or [text]


class Svg:
    def __init__(self, width: int, height: int, title: str):
        self.width = width
        self.height = height
        self.items: list[str] = []
        self.items.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label="{xml_text(title)}">'
        )
        self.items.append(
            """
<defs>
  <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3"
          orient="auto" markerUnits="strokeWidth">
    <path d="M0,0 L0,6 L9,3 z" fill="#27374d"/>
  </marker>
  <marker id="arrowMuted" markerWidth="10" markerHeight="10" refX="9" refY="3"
          orient="auto" markerUnits="strokeWidth">
    <path d="M0,0 L0,6 L9,3 z" fill="#64748b"/>
  </marker>
</defs>
<style>
  .bg { fill: #f8fafc; }
  .title { font: 700 24px var(--font); fill: #102033; }
  .subtitle { font: 500 13px var(--font); fill: #475569; }
  .node { fill: #ffffff; stroke: #334155; stroke-width: 1.4; }
  .nodeAccent { fill: #eef6ff; stroke: #2563eb; stroke-width: 1.4; }
  .nodeWarn { fill: #fff7ed; stroke: #ea580c; stroke-width: 1.4; }
  .nodeStop { fill: #f0fdf4; stroke: #16a34a; stroke-width: 1.4; }
  .nodeText { font: 600 14px var(--font); fill: #0f172a; }
  .smallText { font: 500 12px var(--font); fill: #334155; }
  .edge { stroke: #27374d; stroke-width: 1.5; fill: none; marker-end: url(#arrow); }
  .edgeMuted { stroke: #64748b; stroke-width: 1.3; fill: none; marker-end: url(#arrowMuted); }
  .lifeline { stroke: #94a3b8; stroke-width: 1; stroke-dasharray: 5 5; }
  .message { stroke: #27374d; stroke-width: 1.4; marker-end: url(#arrow); }
  .returnMessage { stroke: #64748b; stroke-width: 1.3; stroke-dasharray: 5 4; marker-end: url(#arrowMuted); }
  .loop { fill: #f1f5f9; stroke: #94a3b8; stroke-width: 1; stroke-dasharray: 6 4; }
</style>
""".replace(
                "var(--font)", FONT
            )
        )
        self.items.append(f'<rect class="bg" x="0" y="0" width="{width}" height="{height}"/>')
        self.text(width / 2, 36, [title], klass="title")

    def rect(self, x: float, y: float, w: float, h: float, klass: str = "node", rx: int = 10):
        self.items.append(f'<rect class="{klass}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>')

    def circle(self, cx: float, cy: float, r: float, fill: str, stroke: str = "#334155", width: float = 1.4):
        self.items.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>'
        )

    def text(
        self,
        x: float,
        y: float,
        lines: list[str],
        klass: str = "nodeText",
        anchor: str = "middle",
        line_height: int = 17,
    ):
        self.items.append(f'<text class="{klass}" x="{x}" y="{y}" text-anchor="{anchor}">')
        for idx, line in enumerate(lines):
            dy = 0 if idx == 0 else line_height
            self.items.append(f'<tspan x="{x}" dy="{dy}">{xml_text(line)}</tspan>')
        self.items.append("</text>")

    def node(self, x: float, y: float, w: float, h: float, label: str, klass: str = "node"):
        self.rect(x, y, w, h, klass=klass)
        lines = wrapped_lines(label, width=18)
        start_y = y + h / 2 - (len(lines) - 1) * 8 + 5
        self.text(x + w / 2, start_y, lines)

    def arrow(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        label: str = "",
        klass: str = "edge",
        bend: float | None = None,
    ):
        if bend is None:
            self.items.append(f'<line class="{klass}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>')
            lx, ly = (x1 + x2) / 2, (y1 + y2) / 2 - 8
        else:
            mx = (x1 + x2) / 2
            self.items.append(
                f'<path class="{klass}" d="M{x1},{y1} C{mx},{y1 + bend} {mx},{y2 + bend} {x2},{y2}"/>'
            )
            lx, ly = mx, (y1 + y2) / 2 + bend / 2 - 8
        if label:
            lines = wrapped_lines(label, width=30)
            pad_w = max(len(line) for line in lines) * 6.5 + 12
            pad_h = len(lines) * 15 + 8
            self.items.append(
                f'<rect x="{lx - pad_w / 2}" y="{ly - 14}" width="{pad_w}" height="{pad_h}" '
                'rx="5" fill="#f8fafc" opacity="0.94"/>'
            )
            self.text(lx, ly, lines, klass="smallText", line_height=15)

    def write(self, name: str):
        self.items.append("</svg>")
        (OUT_DIR / name).write_text("\n".join(self.items), encoding="utf-8")


@dataclass(frozen=True)
class Participant:
    key: str
    label: str


@dataclass(frozen=True)
class Message:
    source: str
    target: str
    label: str
    response: bool = False


@dataclass(frozen=True)
class LoopRange:
    start: int
    end: int
    label: str


def render_top_level_state():
    svg = Svg(1560, 780, "pangu-agent 顶层状态机")
    svg.text(780, 60, ["goal 控制终点，状态迁移由 pangu-agent JSON 输出的 next_action 驱动"], klass="subtitle")

    nodes = {
        "Doctor": (150, 115, 170, 64, "Doctor<br/>环境/认证"),
        "FixConfig": (150, 300, 170, 64, "FixConfig<br/>修复配置"),
        "Scenarios": (430, 115, 180, 64, "Scenarios<br/>选择场景"),
        "TrainingFlow": (720, 115, 190, 68, "TrainingFlow<br/>训练"),
        "ModelPublish": (1010, 115, 190, 68, "ModelPublish<br/>发布模型"),
        "DatasetFlow": (720, 370, 190, 68, "DatasetFlow<br/>数据集准备"),
        "DeploymentFlow": (1010, 370, 190, 68, "DeploymentFlow<br/>部署"),
        "Stop": (1285, 240, 165, 72, "Stop<br/>goal 达成"),
    }

    svg.circle(75, 147, 14, "#0f172a", "#0f172a", 1.4)
    svg.text(75, 190, ["Start"], klass="smallText")
    for key, (x, y, w, h, label) in nodes.items():
        klass = "nodeStop" if key == "Stop" else "nodeAccent" if key in {"TrainingFlow", "DeploymentFlow"} else "node"
        if key == "FixConfig":
            klass = "nodeWarn"
        svg.node(x, y, w, h, label, klass=klass)

    svg.arrow(89, 147, 150, 147)
    svg.arrow(320, 147, 430, 147, "ready")
    svg.arrow(235, 179, 235, 300, "not ready", klass="edgeMuted")
    svg.arrow(150, 332, 92, 160, "retry", klass="edgeMuted", bend=-75)
    svg.arrow(610, 147, 720, 147, "train goal")
    svg.arrow(520, 179, 815, 370, "need dataset", bend=28)
    svg.arrow(815, 370, 815, 183, "goal beyond<br/>dataset_ready")
    svg.arrow(910, 405, 1285, 276, "goal<br/>dataset_ready", klass="edgeMuted", bend=35)
    svg.arrow(910, 149, 1010, 149, "model_published /<br/>service_running")
    svg.arrow(815, 183, 1285, 276, "training_submitted /<br/>training_completed", klass="edgeMuted", bend=22)
    svg.arrow(1200, 149, 1285, 260, "goal<br/>model_published", klass="edgeMuted")
    svg.arrow(1105, 183, 1105, 370, "goal<br/>service_running")
    svg.arrow(1200, 405, 1285, 276, "deployment_submitted /<br/>service_running", klass="edgeMuted")
    svg.arrow(610, 147, 1010, 405, "deploy existing asset", bend=95)

    svg.write("pangu-agent-top-level-state.svg")


def render_sequence(
    name: str,
    title: str,
    participants: list[Participant],
    messages: list[Message],
    loops: list[LoopRange] | None = None,
):
    width = max(980, 180 + len(participants) * 190)
    row_h = 58
    start_y = 158
    height = start_y + len(messages) * row_h + 95
    svg = Svg(width, height, title)

    left = 90
    right = width - 90
    step = (right - left) / (len(participants) - 1)
    positions = {p.key: left + i * step for i, p in enumerate(participants)}
    box_y = 78
    box_w = 142
    box_h = 44
    lifeline_top = box_y + box_h
    lifeline_bottom = height - 50

    for p in participants:
        x = positions[p.key]
        svg.rect(x - box_w / 2, box_y, box_w, box_h, klass="nodeAccent", rx=8)
        svg.text(x, box_y + 27, wrapped_lines(p.label, width=18), klass="nodeText")
        svg.items.append(f'<line class="lifeline" x1="{x}" y1="{lifeline_top}" x2="{x}" y2="{lifeline_bottom}"/>')

    for loop in loops or []:
        y1 = start_y + loop.start * row_h - 31
        y2 = start_y + loop.end * row_h + 24
        svg.items.append(
            f'<rect class="loop" x="48" y="{y1}" width="{width - 96}" height="{y2 - y1}" rx="8"/>'
        )
        svg.text(66, y1 + 20, [f"loop {loop.label}"], klass="smallText", anchor="start")

    for idx, msg in enumerate(messages):
        y = start_y + idx * row_h
        x1 = positions[msg.source]
        x2 = positions[msg.target]
        klass = "returnMessage" if msg.response else "message"
        if msg.source == msg.target:
            loop_x = x1 + 70
            svg.items.append(
                f'<path class="{klass}" d="M{x1},{y} L{loop_x},{y} L{loop_x},{y + 28} L{x1 + 4},{y + 28}"/>'
            )
            label_x = loop_x + 8
            svg.text(label_x, y - 7, wrapped_lines(msg.label, width=34), klass="smallText", anchor="start", line_height=14)
            continue

        svg.items.append(f'<line class="{klass}" x1="{x1}" y1="{y}" x2="{x2}" y2="{y}"/>')
        label_x = (x1 + x2) / 2
        svg.items.append(
            f'<rect x="{label_x - 155}" y="{y - 33}" width="310" height="27" rx="5" '
            'fill="#f8fafc" opacity="0.94"/>'
        )
        svg.text(label_x, y - 16, wrapped_lines(msg.label, width=38), klass="smallText", line_height=14)

    svg.write(name)


def render_dataset_sequence():
    render_sequence(
        "pangu-agent-dataset-publish-sequence.svg",
        "数据集发布时序图",
        [
            Participant("Agent", "Agent"),
            Participant("CLI", "pangu-agent"),
            Participant("State", "Run State"),
            Participant("API", "Pangu API"),
        ],
        [
            Message("Agent", "CLI", "dataset publish-prepare --scenario --goal"),
            Message("CLI", "API", "_query_datasets(catalog=ORIGINAL, status=ONLINE)"),
            Message("CLI", "State", "save sources with index"),
            Message("CLI", "Agent", "sources + next_action", response=True),
            Message("Agent", "CLI", "dataset publish-validate --run-id --source --publish-name"),
            Message("CLI", "State", "save request_body, validate_success=true"),
            Message("CLI", "Agent", "request_body + next_action", response=True),
            Message("Agent", "CLI", "dataset publish-submit --run-id --wait"),
            Message("CLI", "API", "POST PUBLISH_JOBS_PATH"),
            Message("CLI", "API", "_wait_for_published_dataset()"),
            Message("CLI", "API", "_find_ready_training_dataset()"),
            Message("CLI", "API", "_get_dataset_detail(name, catalog=PUBLISH)"),
            Message("CLI", "CLI", "validate_training_dataset_ready()"),
            Message("CLI", "State", "save published_dataset"),
            Message("CLI", "Agent", "published_dataset + terminal/next_action", response=True),
        ],
        loops=[LoopRange(10, 12, "until ready or timeout")],
    )


def render_training_sequence():
    render_sequence(
        "pangu-agent-training-sequence.svg",
        "训练流程时序图",
        [
            Participant("Agent", "Agent"),
            Participant("CLI", "pangu-agent"),
            Participant("State", "Run State"),
            Participant("Raw", "pangu training"),
            Participant("API", "Pangu API"),
        ],
        [
            Message("Agent", "CLI", "train plan --scenario --goal"),
            Message("CLI", "API", "_query_models()"),
            Message("CLI", "API", "_query_datasets(catalog=PUBLISH,status=ONLINE)"),
            Message("CLI", "API", "_query_pools(job_type=train)"),
            Message("CLI", "State", "save indexed candidates"),
            Message("CLI", "Agent", "models/datasets/pools + run_id", response=True),
            Message("Agent", "CLI", "train scaffold --run-id --model --dataset --pool --cards"),
            Message("CLI", "CLI", "select_index()"),
            Message("CLI", "CLI", "_ensure_training_dataset_ready()"),
            Message("CLI", "Raw", "training_scaffold(...)"),
            Message("Raw", "CLI", "train YAML", response=True),
            Message("CLI", "CLI", "load_yaml() + validate_training_context()"),
            Message("CLI", "CLI", "list_training_parameters_from_body()"),
            Message("CLI", "State", "save artifact + selection + params_listed=false"),
            Message("CLI", "Agent", "train_yaml + parameters + next_action=train.params", response=True),
            Message("Agent", "CLI", "train params --run-id"),
            Message("CLI", "State", "params_listed=true, params_artifact_hash=sha256"),
            Message("CLI", "Agent", "full parameters", response=True),
            Message("Agent", "CLI", "train validate --run-id --batch-size --param"),
            Message("CLI", "CLI", "check params_listed and params_artifact_hash"),
            Message("CLI", "CLI", "resolve_training_param_overrides_from_body()"),
            Message("CLI", "Raw", "create_task(dry_run=true)"),
            Message("CLI", "State", "validate_success=true, artifact_hash=sha256"),
            Message("CLI", "Agent", "approval_summary", response=True),
            Message("Agent", "CLI", "train approve --run-id --confirm submit-training"),
            Message("CLI", "State", "record_approval()"),
            Message("Agent", "CLI", "train submit --run-id"),
            Message("CLI", "CLI", "require_approval() + _require_artifact_hash()"),
            Message("CLI", "Raw", "create_task(dry_run=false)"),
            Message("CLI", "State", "save submit_result"),
            Message("CLI", "Agent", "task + terminal/next_action", response=True),
        ],
    )


def render_publish_sequence():
    render_sequence(
        "pangu-agent-model-publish-sequence.svg",
        "模型发布与部署资产解析时序图",
        [
            Participant("Agent", "Agent"),
            Participant("CLI", "pangu-agent"),
            Participant("Raw", "pangu training"),
            Participant("API", "Pangu API"),
            Participant("State", "Run State"),
        ],
        [
            Message("Agent", "CLI", "train publish --run-id --task-id --asset-name --confirm publish-model"),
            Message("CLI", "Raw", "publish_model(...)"),
            Message("Raw", "CLI", "publish_result.model_id", response=True),
            Message("CLI", "API", "_resolve_published_asset(model_id, asset_name)"),
            Message("API", "CLI", "model-assets-ext assets", response=True),
            Message("CLI", "CLI", "select_published_asset()"),
            Message("CLI", "State", "save published_asset"),
            Message("CLI", "Agent", "published_model_id + published_asset_id + deploy_plan_command", response=True),
        ],
    )


def render_deploy_sequence():
    render_sequence(
        "pangu-agent-deployment-sequence.svg",
        "部署流程时序图",
        [
            Participant("Agent", "Agent"),
            Participant("CLI", "pangu-agent"),
            Participant("API", "Pangu API"),
            Participant("Raw", "pangu service"),
            Participant("State", "Run State"),
        ],
        [
            Message("Agent", "CLI", "deploy plan --asset-id --goal"),
            Message("CLI", "API", "GET model asset detail"),
            Message("CLI", "CLI", "_extract_resource_info()"),
            Message("CLI", "API", "_query_pools(purpose=infer)"),
            Message("CLI", "State", "save deploy_options and pools"),
            Message("CLI", "Agent", "deploy_options + pools", response=True),
            Message("Agent", "CLI", "deploy scaffold --run-id --option --pool --service-name"),
            Message("CLI", "Raw", "scaffold_deploy(...)"),
            Message("Raw", "CLI", "deploy YAML", response=True),
            Message("CLI", "State", "save deploy_yaml"),
            Message("Agent", "CLI", "deploy validate --run-id"),
            Message("CLI", "CLI", "yaml_has_todo() + required field checks"),
            Message("CLI", "State", "validate_success=true, artifact_hash=sha256"),
            Message("CLI", "Agent", "approval_summary", response=True),
            Message("Agent", "CLI", "deploy approve --run-id --confirm deploy-service"),
            Message("CLI", "State", "record_approval()"),
            Message("Agent", "CLI", "deploy submit --run-id"),
            Message("CLI", "CLI", "require_approval()"),
            Message("CLI", "Raw", "deploy_service(...)"),
            Message("CLI", "State", "save submit_result"),
            Message("CLI", "Agent", "service + terminal/next_action", response=True),
        ],
    )


def main():
    render_top_level_state()
    render_dataset_sequence()
    render_training_sequence()
    render_publish_sequence()
    render_deploy_sequence()


if __name__ == "__main__":
    main()
