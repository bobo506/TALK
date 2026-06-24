"""Hall 类型 -> 软预设模板注册表（DELIBERATION §3）。

软预设 = 注入流程指引，非硬状态机；领域中立初版，后续可由 `.talk/` 覆盖。
"""

from __future__ import annotations

from typing import Any

HALL_TYPE_TEMPLATES: dict[str, dict[str, Any]] = {
    "free": {
        "label": "自由",
        "protocol_guidance": "自由交流 Hall，无固定流程。成员按需提问、回应、分享信息，不强制轮次或表态。",
        "roles": [],
    },
    "task": {
        "label": "任务",
        "protocol_guidance": (
            "任务协调 Hall：目标 -> 拆解 -> 分派 -> 执行 -> 收口。"
            "决策人（群内 decision_tier=decision 的成员或 human）负责拍板与验收；"
            "执行成员认领切片、完成后在 Hall 汇报。"
        ),
        "roles": [
            {"role": "lead", "norm": "拆解任务、分派、把控验收与收口"},
            {"role": "executor", "norm": "认领分派的执行切片，完成后在 Hall 汇报"},
        ],
    },
    "brainstorm": {
        "label": "头脑风暴",
        "protocol_guidance": (
            "头脑风暴 Hall：主持人抛出主题（question），参与者各自给出具体想法（answer）；"
            "被 @所有人 时直接给实质想法，不回'收到'。随后用 agree / optimize / disagree "
            "互相补充与碰撞。先发散、暂缓评判，最后由决策人归纳产出结论（decision）收口。"
        ),
        "roles": [
            {"role": "facilitator", "norm": "抛出主题、控制节奏、最后归纳产出 decision"},
            {"role": "contributor", "norm": "围绕主题给出具体想法（answer），并对他人想法做 optimize / agree / disagree"},
        ],
    },
    "review": {
        "label": "评审",
        "protocol_guidance": (
            "评审 Hall：作者提交标的产物，评审人针对产物给出收敛式批评与改进意见"
            "（disagree / optimize，对事不对人）；作者据此修订。"
            "最后由决策人产出结论（decision）收口。先收敛、给可执行意见。"
        ),
        "roles": [
            {"role": "author", "norm": "提交标的产物、回应评审意见并修订"},
            {"role": "reviewer", "norm": "针对产物给出收敛式批评与改进建议（disagree / optimize）"},
        ],
    },
}

HALL_TYPES: frozenset[str] = frozenset(HALL_TYPE_TEMPLATES)
DEFAULT_HALL_TYPE = "free"
