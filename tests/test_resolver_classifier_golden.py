"""Golden corpus and deterministic snapshot tests for resolver classifier."""


from pathlib import Path
import unittest
import json

from pnp import resolver_classifier


FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "resolver_classifier_golden.json"
SNAPSHOT = FIXTURES / "resolver_classifier_snapshot_v1.json"


def _load_json(path: Path) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


class ResolverClassifierGoldenTests(unittest.TestCase):
    def setUp(self) -> None:
        resolver_classifier.reset_telemetry()

    def test_golden_corpus_matches_expected_classifications(self) -> None:
        cases = _load_json(GOLDEN)
        for case in cases:
            name = str(case["name"])
            stderr = str(case["stderr"])
            expected = case["expected"]
            got = resolver_classifier.classify_stderr(stderr)
            self.assertEqual(got, expected, msg=name)

    def test_snapshot_is_stable_and_deterministic(self) -> None:
        cases = _load_json(GOLDEN)
        expected_snapshot = _load_json(SNAPSHOT)

        first = []
        second = []
        for case in cases:
            name = str(case["name"])
            stderr = str(case["stderr"])
            first.append(
                {
                    "name": name,
                    "classification": resolver_classifier.classify_stderr(stderr),
                }
            )
        resolver_classifier.reset_telemetry()
        for case in cases:
            name = str(case["name"])
            stderr = str(case["stderr"])
            second.append(
                {
                    "name": name,
                    "classification": resolver_classifier.classify_stderr(stderr),
                }
            )

        self.assertEqual(first, second)
        self.assertEqual(first, expected_snapshot)

    def test_ambiguous_case_increments_conflict_counter(self) -> None:
        payload = resolver_classifier.classify_stderr(
            "fatal: could not resolve host github.com and invalid object deadbeef"
        )
        self.assertEqual(payload["code"], "PNP_NET_CONNECTIVITY")
        self.assertEqual(resolver_classifier.rule_conflict_count(), 1)


if __name__ == "__main__":
    unittest.main()
