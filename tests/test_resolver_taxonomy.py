"""Resolver classification and taxonomy stability tests."""


from unittest.mock import patch
import unittest

from pnp import resolver_classifier
from pnp import resolver, utils


class ResolverTaxonomyTests(unittest.TestCase):
    def setUp(self) -> None:
        resolver.reset_resolver_telemetry()

    def test_classify_network_connectivity(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: could not resolve host: github.com")
        self.assertEqual(cls.code, "PNP_NET_CONNECTIVITY")
        self.assertEqual(cls.severity, "error")
        self.assertEqual(cls.handler, "internet_con_err")

    def test_classify_dubious_ownership(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: detected dubious ownership in repository")
        self.assertEqual(cls.code, "PNP_GIT_DUBIOUS_OWNERSHIP")
        self.assertEqual(cls.severity, "warn")
        self.assertEqual(cls.handler, "dubious_ownership")

    def test_classify_invalid_object(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: invalid object 123")
        self.assertEqual(cls.code, "PNP_GIT_INVALID_OBJECT")
        self.assertEqual(cls.severity, "error")
        self.assertEqual(cls.handler, "invalid_object")

    def test_classify_remote_url_invalid(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: could not read from remote repository https://bad")
        self.assertEqual(cls.code, "PNP_NET_REMOTE_URL_INVALID")
        self.assertEqual(cls.handler, "internet_con_err")

    def test_classify_remote_unreadable(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: could not read from remote repository")
        self.assertEqual(cls.code, "PNP_NET_REMOTE_UNREADABLE")
        self.assertEqual(cls.handler, "missing_remote")

    def test_classify_auth_failure(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: Authentication failed for 'https://github.com/u/r.git'")
        self.assertEqual(cls.code, "PNP_NET_AUTH_FAIL")
        self.assertEqual(cls.handler, "auth_failure")

    def test_classify_large_file_rejected(self) -> None:
        h = resolver.Handlers()
        cls = h.classify(
            "remote: error: File build/app.bin is 120.00 MB; this exceeds GitHub's file size limit of 100.00 MB"
        )
        self.assertEqual(cls.code, "PNP_NET_LARGE_FILE_REJECTED")
        self.assertEqual(cls.handler, "large_file_rejection")

    def test_classify_hook_declined(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("error: pre-push hook declined")
        self.assertEqual(cls.code, "PNP_GIT_HOOK_DECLINED")
        self.assertEqual(cls.handler, "hook_declined")

    def test_classify_submodule_inconsistent(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: remote error: upload-pack: not our ref deadbeef")
        self.assertEqual(cls.code, "PNP_GIT_SUBMODULE_INCONSISTENT")
        self.assertEqual(cls.handler, "submodule_inconsistent")

    def test_classify_non_fast_forward(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("! [rejected] main -> main (non-fast-forward)")
        self.assertEqual(cls.code, "PNP_GIT_NON_FAST_FORWARD")
        self.assertEqual(cls.handler, "diverged_branch")

    def test_classify_protected_branch(self) -> None:
        h = resolver.Handlers()
        cls = h.classify(
            "remote: error: GH006: Protected branch update failed for refs/heads/main"
        )
        self.assertEqual(cls.code, "PNP_GIT_PROTECTED_BRANCH")
        self.assertEqual(cls.handler, "protected_branch")

    def test_classify_dirty_worktree(self) -> None:
        h = resolver.Handlers()
        cls = h.classify(
            "error: Your local changes to the following files would be overwritten by merge"
        )
        self.assertEqual(cls.code, "PNP_GIT_DIRTY_WORKTREE")
        self.assertEqual(cls.handler, "dirty_worktree")

    def test_classify_detached_head(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: You are not currently on a branch.")
        self.assertEqual(cls.code, "PNP_GIT_DETACHED_HEAD")
        self.assertEqual(cls.handler, "detached_head")

    def test_classify_line_ending_normalization(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("warning: in the working copy of 'x.py', LF will be replaced by CRLF")
        self.assertEqual(cls.code, "PNP_GIT_LINE_ENDING_NORMALIZATION")
        self.assertEqual(cls.handler, "line_endings")

    def test_classify_index_worktree_mismatch(self) -> None:
        h = resolver.Handlers()
        cls = h.classify(
            "error: short read while indexing NUL\n"
            "error: unable to index 'NUL'\n"
            "fatal: unable to stat 'missing/file.txt': No such file or directory"
        )
        self.assertEqual(cls.code, "PNP_GIT_INDEX_WORKTREE_MISMATCH")
        self.assertEqual(cls.handler, "index_worktree_mismatch")

    def test_classify_ref_conflict(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("error: cannot lock ref 'refs/tags/v1.0.0': reference already exists")
        self.assertEqual(cls.code, "PNP_GIT_REF_CONFLICT")
        self.assertEqual(cls.handler, "ref_conflict")

    def test_classify_lock_contention(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: Unable to create '.git/index.lock': File exists")
        self.assertEqual(cls.code, "PNP_GIT_LOCK_CONTENTION")
        self.assertEqual(cls.handler, "lock_contention")

    def test_classify_upstream_missing(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: The current branch main has no upstream branch.")
        self.assertEqual(cls.code, "PNP_GIT_UPSTREAM_MISSING")
        self.assertEqual(cls.handler, "upstream_missing")

    def test_classify_tls_failure(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: server certificate verification failed")
        self.assertEqual(cls.code, "PNP_NET_TLS_FAIL")
        self.assertEqual(cls.handler, "internet_con_err")

    def test_classify_timeout(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: Operation timed out after 120000 milliseconds")
        self.assertEqual(cls.code, "PNP_NET_TIMEOUT")
        self.assertEqual(cls.handler, "internet_con_err")

    def test_classify_unclassified(self) -> None:
        payload = resolver.classify_stderr("fatal: some brand new git error")
        self.assertEqual(payload["code"], "PNP_GIT_UNCLASSIFIED")
        self.assertEqual(payload["severity"], "warn")
        self.assertEqual(payload["handler"], "fallback")
        telemetry = resolver.resolver_telemetry()
        self.assertEqual(telemetry["unknown_classifications"], 1)
        self.assertEqual(telemetry["rule_conflicts"], 0)

    def test_normalize_stderr_redacts_urls_and_tokens(self) -> None:
        raw = "fatal: could not read from remote repository https://ghp_abcd1234@github.com/u/r.git"
        normalized = resolver_classifier.normalize_stderr(raw)
        self.assertNotIn("ghp_abcd1234", normalized)
        self.assertIn("<url>", normalized)

    def test_classification_stable_across_stderr_variants(self) -> None:
        cases: list[tuple[str, str]] = [
            ("fatal:   could not resolve host: github.com", "PNP_NET_CONNECTIVITY"),
            ("FATAL:\nCould Not Resolve Host:\tGitHub.com", "PNP_NET_CONNECTIVITY"),
            ("fatal: detected dubious ownership in repository", "PNP_GIT_DUBIOUS_OWNERSHIP"),
            ("fatal: could not read from remote repository https://github.com/u/r.git", "PNP_NET_REMOTE_URL_INVALID"),
            ("fatal: could not read from remote repository https://ghp_secret@github.com/u/r.git", "PNP_NET_REMOTE_URL_INVALID"),
            ("fatal: could not read from remote repository", "PNP_NET_REMOTE_UNREADABLE"),
            ("fatal: Authentication failed for 'https://github.com/u/r.git'", "PNP_NET_AUTH_FAIL"),
            (
                "remote: error: File build/app.bin is 120.00 MB; this exceeds GitHub's file size limit of 100.00 MB",
                "PNP_NET_LARGE_FILE_REJECTED",
            ),
            ("error: pre-push hook declined", "PNP_GIT_HOOK_DECLINED"),
            ("fatal: remote error: upload-pack: not our ref deadbeef", "PNP_GIT_SUBMODULE_INCONSISTENT"),
            ("! [rejected] main -> main (non-fast-forward)", "PNP_GIT_NON_FAST_FORWARD"),
            (
                "remote: error: GH006: Protected branch update failed for refs/heads/main",
                "PNP_GIT_PROTECTED_BRANCH",
            ),
            (
                "error: Your local changes to the following files would be overwritten by merge",
                "PNP_GIT_DIRTY_WORKTREE",
            ),
            (
                "warning: in the working copy of 'x.py', LF will be replaced by CRLF",
                "PNP_GIT_LINE_ENDING_NORMALIZATION",
            ),
            (
                "error: short read while indexing NUL\nerror: unable to index 'NUL'\n"
                "fatal: unable to stat 'missing/file.txt': No such file or directory",
                "PNP_GIT_INDEX_WORKTREE_MISMATCH",
            ),
            ("fatal: You are not currently on a branch.", "PNP_GIT_DETACHED_HEAD"),
            ("error: cannot lock ref 'refs/tags/v1.0.0': reference already exists", "PNP_GIT_REF_CONFLICT"),
            ("fatal: Unable to create '.git/index.lock': File exists", "PNP_GIT_LOCK_CONTENTION"),
            ("fatal: The current branch main has no upstream branch.", "PNP_GIT_UPSTREAM_MISSING"),
            ("fatal: server certificate verification failed", "PNP_NET_TLS_FAIL"),
            ("fatal: Operation timed out after 120000 milliseconds", "PNP_NET_TIMEOUT"),
        ]
        h = resolver.Handlers()
        for stderr, expected in cases:
            cls = h.classify(stderr)
            self.assertEqual(cls.code, expected)

    def test_rule_conflict_counter_increments_for_multi_code_match(self) -> None:
        conflict_rule = resolver_classifier.ClassificationRule(
            code="PNP_GIT_UNCLASSIFIED",
            handler="fallback",
            matcher=lambda s: "could not resolve host" in s,
        )
        rules = resolver_classifier.CLASSIFICATION_RULES + (conflict_rule,)
        with patch.object(resolver_classifier, "CLASSIFICATION_RULES", rules):
            payload = resolver.classify_stderr("fatal: could not resolve host: github.com")
        self.assertEqual(payload["code"], "PNP_NET_CONNECTIVITY")
        telemetry = resolver.resolver_telemetry()
        self.assertEqual(telemetry["rule_conflicts"], 1)

    def test_dispatch_records_last_error_metadata(self) -> None:
        h = resolver.Handlers()
        with patch.object(h, "missing_remote",
                          return_value=utils.StepResult.RETRY):
            result = h("fatal: could not read from remote repository", ".")
        self.assertIs(result, utils.StepResult.RETRY)
        assert h.last_error is not None
        self.assertEqual(h.last_error["code"], "PNP_NET_REMOTE_UNREADABLE")

    def test_decide_returns_typed_policy_decision(self) -> None:
        h = resolver.Handlers()
        with patch.object(h, "missing_remote",
                          return_value=utils.StepResult.RETRY):
            decision = h.decide("fatal: could not read from remote repository", ".")
        self.assertIs(decision.result, utils.StepResult.RETRY)
        self.assertEqual(decision.classification.code, "PNP_NET_REMOTE_UNREADABLE")
        self.assertTrue(decision.handled)
        assert h.last_decision is not None
        self.assertIs(h.last_decision.result, utils.StepResult.RETRY)

    def test_decide_internet_error_sets_last_decision_before_raise(self) -> None:
        h = resolver.Handlers()
        with patch.object(h, "internet_con_err",
                          side_effect=RuntimeError("stop")):
            with self.assertRaises(RuntimeError):
                h.decide("fatal: could not resolve host: github.com", ".")
        assert h.last_decision is not None
        self.assertIs(h.last_decision.result, utils.StepResult.FAIL)
        self.assertEqual(h.last_decision.classification.code,
                         "PNP_NET_CONNECTIVITY")


if __name__ == "__main__":
    unittest.main()
