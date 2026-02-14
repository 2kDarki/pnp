"""Resolver classification and taxonomy stability tests."""
from __future__ import annotations

from unittest.mock import patch
import unittest

from pnp import resolver, utils


class ResolverTaxonomyTests(unittest.TestCase):
    def test_classify_network_connectivity(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: could not resolve host: github.com")
        self.assertEqual(cls.code, "PNP_RES_NETWORK_CONNECTIVITY")
        self.assertEqual(cls.severity, "error")
        self.assertEqual(cls.handler, "internet_con_err")

    def test_classify_dubious_ownership(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: detected dubious ownership in repository")
        self.assertEqual(cls.code, "PNP_RES_DUBIOUS_OWNERSHIP")
        self.assertEqual(cls.severity, "warn")
        self.assertEqual(cls.handler, "dubious_ownership")

    def test_classify_invalid_object(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: invalid object 123")
        self.assertEqual(cls.code, "PNP_RES_INVALID_OBJECT")
        self.assertEqual(cls.severity, "error")
        self.assertEqual(cls.handler, "invalid_object")

    def test_classify_remote_url_invalid(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: could not read from remote repository https://bad")
        self.assertEqual(cls.code, "PNP_RES_REMOTE_URL_INVALID")
        self.assertEqual(cls.handler, "internet_con_err")

    def test_classify_remote_unreadable(self) -> None:
        h = resolver.Handlers()
        cls = h.classify("fatal: could not read from remote repository")
        self.assertEqual(cls.code, "PNP_RES_REMOTE_UNREADABLE")
        self.assertEqual(cls.handler, "missing_remote")

    def test_classify_unclassified(self) -> None:
        payload = resolver.classify_stderr("fatal: some brand new git error")
        self.assertEqual(payload["code"], "PNP_RES_UNCLASSIFIED")
        self.assertEqual(payload["severity"], "warn")
        self.assertEqual(payload["handler"], "fallback")

    def test_dispatch_records_last_error_metadata(self) -> None:
        h = resolver.Handlers()
        with patch.object(h, "missing_remote",
                          return_value=utils.StepResult.RETRY):
            result = h("fatal: could not read from remote repository", ".")
        self.assertIs(result, utils.StepResult.RETRY)
        assert h.last_error is not None
        self.assertEqual(h.last_error["code"], "PNP_RES_REMOTE_UNREADABLE")


if __name__ == "__main__":
    unittest.main()
