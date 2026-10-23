"""Finite code-owned runtime/host diagnostic categories (no prefix trust)."""

RUNTIME_ERROR_CODES = frozenset({
    "runtime_already_running", "runtime_api_already_running", "runtime_api_control_missing",
    "runtime_api_control_required", "runtime_api_exited", "runtime_api_not_owned",
    "runtime_api_not_ready", "runtime_api_stop_timeout", "runtime_argv_invalid",
    "runtime_config_invalid", "runtime_existing_drain_marker", "runtime_host_config_invalid",
    "runtime_host_path_escape", "runtime_host_stop_timeout", "runtime_key_root_inside_project",
    "runtime_loopback_required", "runtime_manager_not_drained", "runtime_not_running",
    "runtime_operator_not_human", "runtime_path_invalid", "runtime_project_missing",
    "runtime_role_stop_timeout", "runtime_stop_marker_requires_review",
    "runtime_workbuddy_config_invalid", "runtime_worker_stop_timeout",
})

HOST_ERROR_CODES = frozenset({
    "binding_fingerprint_mismatch", "choice_unverified", "cli_command_unresolved", "cli_executable_option_unsupported",
    "cli_incompatible", "cli_missing", "execution_timeout_invalid", "host_unreachable",
    "identity_mismatch", "member_required", "model_alias_unresolved", "operator_key_missing",
    "ownership_lock_busy", "profile_missing", "readiness_timeout", "role_facts_unavailable",
    "role_key_missing", "runtime_alias_unsupported", "runtime_template_conflict",
    "runtime_template_empty", "runtime_template_invalid", "runtime_template_missing_model",
    "runtime_template_unsupported", "runtime_unverified", "state_dir_insecure", "storage_unavailable",
})
