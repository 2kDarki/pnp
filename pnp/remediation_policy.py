"""Policy matrix for resolver remediation actions."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RemediationRule:
    """Execution policy for a remediation action."""
    destructive: bool
    allow_ci: bool
    allow_autofix: bool
    requires_interactive: bool
    requires_confirmation: bool


REMEDIATION_POLICY: dict[str, RemediationRule] = {
    "git_safe_directory": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=True,
    ),
    "open_shell_manual": RemediationRule(
        destructive=False,
        allow_ci=False,
        allow_autofix=False,
        requires_interactive=True,
        requires_confirmation=True,
    ),
    "destructive_reset": RemediationRule(
        destructive=True,
        allow_ci=False,
        allow_autofix=False,
        requires_interactive=True,
        requires_confirmation=True,
    ),
    "safe_fix_network": RemediationRule(
        destructive=False,
        allow_ci=False,
        allow_autofix=False,
        requires_interactive=True,
        requires_confirmation=True,
    ),
    "skip_continue": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "abort": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "add_origin_https": RemediationRule(
        destructive=False,
        allow_ci=False,
        allow_autofix=False,
        requires_interactive=True,
        requires_confirmation=True,
    ),
    "add_origin_ssh": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "add_origin_token": RemediationRule(
        destructive=False,
        allow_ci=False,
        allow_autofix=False,
        requires_interactive=True,
        requires_confirmation=True,
    ),
    "open_token_page": RemediationRule(
        destructive=False,
        allow_ci=False,
        allow_autofix=False,
        requires_interactive=True,
        requires_confirmation=False,
    ),
    "stale_lock_cleanup": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "set_upstream_tracking": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "create_feature_branch": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "recover_detached_head": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "auto_stash_worktree": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "auto_stash_pop": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "auto_wip_commit": RemediationRule(
        destructive=False,
        allow_ci=False,
        allow_autofix=False,
        requires_interactive=True,
        requires_confirmation=True,
    ),
    "create_gitattributes": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "renormalize_line_endings": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "index_rebuild_restage": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    # Nuclear fallback: wipe the index with `git rm --cached -r .` and
    # re-add with core.autocrlf=false.  Only the index is affected; the
    # working tree is never touched, so this is safe to run unattended.
    "index_nuke_rebuild": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "configure_git_lfs_tracking": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "history_scrub_guidance": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "pull_rebase": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "push_no_verify": RemediationRule(
        destructive=False,
        allow_ci=False,
        allow_autofix=False,
        requires_interactive=True,
        requires_confirmation=True,
    ),
    "submodule_sync_update": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
    "submodule_fetch_prune": RemediationRule(
        destructive=False,
        allow_ci=True,
        allow_autofix=True,
        requires_interactive=False,
        requires_confirmation=False,
    ),
}


def can_run_remediation(
    action: str,
    ci_mode: bool,
    autofix: bool,
    interactive: bool,
) -> tuple[bool, str]:
    """Validate whether a remediation action is allowed in context."""
    rule = REMEDIATION_POLICY.get(action)
    if rule is None:
        return False, "unknown remediation action"
    if ci_mode and not rule.allow_ci:
        return False, "action disabled in CI mode"
    if autofix and not rule.allow_autofix:
        return False, "action disabled in auto-fix mode"
    if rule.requires_interactive and not interactive:
        return False, "action requires interactive mode"
    return True, ""


def requires_confirmation(action: str, autofix: bool) -> bool:
    """Whether a remediation action needs explicit confirmation prompt."""
    rule = REMEDIATION_POLICY.get(action)
    if rule is None: return False
    if autofix: return False
    return rule.requires_confirmation
