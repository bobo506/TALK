import pytest

from bridges import antigravity_effort as ae


REAL_AGY_MODELS_SAMPLE = """\
Fetching available models...
gemini-4-neon-high\tGemini 4 Neon (High)
gemini-4-neon-xhigh\tGemini 4 Neon (XHigh)
gemini-4-neon-medium\tGemini 4 Neon (Medium)
gemini-4-neon-low\tGemini 4 Neon (Low)
gemini-4-carbon-medium\tGemini 4 Carbon (Medium)
gemini-4-carbon-high\tGemini 4 Carbon (High)
gemini-4-carbon-low\tGemini 4 Carbon (Low)
gemini-4-argon-high\tGemini 4 Argon (High)
gemini-4-hydrogen-high\tGemini 4 Hydrogen (High)
gemini-4-hydrogen-xhigh\tGemini 4 Hydrogen (XHigh)
gemini-4-hydrogen-medium\tGemini 4 Hydrogen (Medium)
gemini-4-hydrogen-low\tGemini 4 Hydrogen (Low)
claude-opus-5-5-high\tClaude Opus 5.5 (High)
gpt-oss-120b-medium\tGPT-OSS 120B (Medium)
"""


def test_parse_model_id_valid_and_invalid():
    assert ae.parse_model_id("gemini-4-neon") == ("gemini-4-neon", None)
    assert ae.parse_model_id("gemini-4-neon-xhigh") == ("gemini-4-neon", "xhigh")
    assert ae.parse_model_id("gemini-4-carbon-high") == ("gemini-4-carbon", "high")
    assert ae.parse_model_id("gemini-4-hydrogen-low") == ("gemini-4-hydrogen", "low")
    # Carbon only supports low / medium / high — xhigh must be rejected fail-closed.
    assert ae.parse_model_id("gemini-4-carbon-xhigh") is None
    assert ae.parse_model_id("gemini-4-argon-high") is None
    assert ae.parse_model_id("gemini-4-neon-max") is None
    assert ae.parse_model_id("") is None
    assert ae.parse_model_id(None) is None


def test_cli_model_id_synthesis():
    assert ae.cli_model_id("gemini-4-neon", "xhigh") == "gemini-4-neon-xhigh"
    assert ae.cli_model_id("gemini-4-carbon", "medium") == "gemini-4-carbon-medium"
    assert ae.cli_model_id("gemini-4-hydrogen") == "gemini-4-hydrogen-high"
    assert ae.cli_model_id("gemini-4-hydrogen-low") == "gemini-4-hydrogen-low"
    with pytest.raises(ae.AntigravityEffortUnavailable) as exc:
        ae.cli_model_id("gemini-4-carbon", "xhigh")
    assert exc.value.reason == "antigravity_effort_unsupported"
    with pytest.raises(ae.AntigravityEffortUnavailable) as exc:
        ae.cli_model_id("gemini-4-carbon-xhigh")
    assert exc.value.reason == "antigravity_effort_unsupported"
    with pytest.raises(ae.AntigravityEffortUnavailable) as exc:
        ae.cli_model_id("gemini-4-argon", "high")
    assert exc.value.reason == "antigravity_model_unsupported"


def test_parse_agy_models_output_filters_to_three_target_models():
    catalog = ae.parse_agy_models_output(REAL_AGY_MODELS_SAMPLE)
    assert [item["model_id"] for item in catalog] == [
        "gemini-4-neon",
        "gemini-4-carbon",
        "gemini-4-hydrogen",
    ]
    by_id = {item["model_id"]: item for item in catalog}
    assert by_id["gemini-4-neon"]["supported_efforts"] == ["low", "medium", "high", "xhigh"]
    assert by_id["gemini-4-carbon"]["supported_efforts"] == ["low", "medium", "high"]
    assert by_id["gemini-4-hydrogen"]["supported_efforts"] == ["low", "medium", "high", "xhigh"]
    assert by_id["gemini-4-carbon"]["default_effort"] == "high"
    assert by_id["gemini-4-neon"]["cli_model_ids"]["xhigh"] == "gemini-4-neon-xhigh"


def test_parse_agy_models_output_does_not_fabricate_missing_efforts():
    partial = "gemini-4-carbon-low\tGemini 4 Carbon (Low)\ngemini-4-carbon-medium\tGemini 4 Carbon (Medium)\n"
    catalog = ae.parse_agy_models_output(partial)
    assert len(catalog) == 1
    assert catalog[0]["supported_efforts"] == ["low", "medium"]
    assert catalog[0]["default_effort"] == "low"


def test_resolve_binding_effort_rules():
    binding = {
        "model_id": "gemini-4-neon",
        "effective_effort": "xhigh",
        "effort_override": "xhigh",
        "effort_options": ["low", "medium", "high", "xhigh"],
        "effort_source": "catalog",
    }
    assert ae.resolve_binding_effort(binding) == ("xhigh", ae.EFFORT_SOURCE_USER)

    # Carbon rejects xhigh even if binding lists it.
    carbon_bad = {
        "model_id": "gemini-4-carbon",
        "effective_effort": "xhigh",
        "effort_override": "xhigh",
        "effort_options": ["low", "medium", "high", "xhigh"],
        "effort_source": "adapter",
    }
    with pytest.raises(ae.AntigravityEffortUnavailable) as exc:
        ae.resolve_binding_effort(carbon_bad)
    assert exc.value.reason == "antigravity_effort_unsupported"

    # Override without source or options is refused as unknown.
    no_source = {
        "model_id": "gemini-4-neon",
        "effective_effort": "high",
        "effort_override": "high",
        "effort_options": ["low", "high"],
    }
    with pytest.raises(ae.AntigravityEffortUnavailable) as exc:
        ae.resolve_binding_effort(no_source)
    assert exc.value.reason == "antigravity_effort_capability_unknown"

    # Fallback when effective_effort is absent.
    legacy = {"model_id": "gemini-4-hydrogen"}
    assert ae.resolve_binding_effort(legacy, "medium") == ("medium", ae.EFFORT_SOURCE_CONFIG)


def test_apply_effort_rewrites_model_and_flag_safely():
    cmd = "'C:\\Program Files\\agy\\agy.exe' --mode auto --model gemini-4-neon-high --effort high -p"
    updated, mode = ae.apply_effort(cmd, "xhigh")
    assert mode == "model_and_flag"
    assert "--model gemini-4-neon-xhigh" in updated
    assert "--effort xhigh" in updated
    assert "C:\\Program Files\\agy\\agy.exe" in updated

    tokens = ["agy", "--model", "gemini-4-carbon-high", "-p"]
    updated_tokens, mode = ae.apply_effort(tokens, "low")
    assert mode == "model"
    assert updated_tokens == ["agy", "--model", "gemini-4-carbon-low", "-p"]

    with pytest.raises(ae.AntigravityEffortUnavailable):
        ae.apply_effort(tokens, "xhigh")

    unknown = ["custom-tool", "--prompt"]
    assert ae.apply_effort(unknown, "low") == (unknown, "unchanged")


def test_apply_effort_hardening_equals_repeated_and_mismatch():
    # Go-style --flag=value syntax must be rewritten and validated (Carbon rejects xhigh).
    eq_cmd = "agy --model=gemini-4-carbon-high --effort=high -p"
    updated, mode = ae.apply_effort(eq_cmd, "medium")
    assert mode == "model_and_flag"
    assert "--model=gemini-4-carbon-medium" in updated
    assert "--effort=medium" in updated
    with pytest.raises(ae.AntigravityEffortUnavailable) as exc:
        ae.apply_effort(eq_cmd, "xhigh")
    assert exc.value.reason == "antigravity_effort_unsupported"

    # Unsupported model in command must not be skipped to rewrite only --effort.
    with pytest.raises(ae.AntigravityEffortUnavailable) as exc:
        ae.apply_effort(["agy", "--model", "gemini-4-argon-high", "--effort", "high", "-p"], "low")
    assert exc.value.reason == "antigravity_model_unsupported"

    # Contradictory base_model must fail closed instead of silently swapping model families.
    with pytest.raises(ae.AntigravityEffortUnavailable) as exc:
        ae.apply_effort(["agy", "--model", "gemini-4-carbon-high", "--effort", "high", "-p"], "low", base_model="gemini-4-neon")
    assert exc.value.reason == "antigravity_model_mismatch"

    # Repeated flags must all be rewritten consistently.
    repeated = ["agy", "--model", "gemini-4-neon-low", "--model=gemini-4-neon-medium", "--effort", "low", "--effort=medium", "-p"]
    rewritten, mode = ae.apply_effort(repeated, "xhigh")
    assert mode == "model_and_flag"
    assert rewritten == [
        "agy", "--model", "gemini-4-neon-xhigh", "--model=gemini-4-neon-xhigh",
        "--effort", "xhigh", "--effort=xhigh", "-p",
    ]
