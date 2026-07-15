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
            "头脑风暴 Hall，流程分四步：① 发起人提出需求；"
            "② 每位成员（包括决策人）各给出一条具体想法（answer），被 @所有人 时直接给实质想法、不回'收到'；"
            "③ 按发起人指示，对指定成员的想法逐一表态：同意用 agree，否决用 disagree 且必须给出你自己的看法；"
            "④ 全部想法表态完成后，由决策人汇总全场想法与表态，产出唯一结论（decision）收口。"
            "未轮到表态或汇总时不要抢跑。"
        ),
        "roles": [
            {"role": "facilitator", "norm": "先与大家一样贡献想法；等发起人指示后，汇总全场想法与表态，产出唯一结论（decision）"},
            {"role": "contributor", "norm": "给出具体想法（answer）；被点名表态时对指定想法明确 agree 或 disagree（否决必须附自己的看法）"},
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
