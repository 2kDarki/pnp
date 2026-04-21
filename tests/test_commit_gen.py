"""Unit tests for AI-powered commit message generation."""
from unittest.mock import Mock, patch
import unittest
import json
import os

import requests

from pnp.commit_gen import (
    MAX_DIFF_CHARS,
    MODELS,
    _call_openrouter,
    _get_api_key,
    _trim_diff,
    generate_commit_message,
)


SAMPLE_DIFF = """diff --git a/file.py b/file.py
index 1234567..abcdefg 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,5 @@
+import requests
+
 def foo():
-    pass
+    return 42
"""

SAMPLE_RESPONSE = {
    "choices": [{
        "message": {
            "content":
          		"feat(api): add request handling\n\n"

                "Changes:\n"
                "  - Import requests library\n"
          		"  - Update foo() to return value"
        },
        "finish_reason": "stop"
    }]
}

LARGE_DIFF = "x" * 100001


class CommitGenTests(unittest.TestCase):
    # ===========================================================
    # Tests for _trim_diff
    # ===========================================================

    def test_trim_diff_under_limit_returns_unchanged(self) -> None:
        diff   = "a" * 50000
        result = _trim_diff(diff)
        self.assertEqual(result, diff)

    def test_trim_diff_over_limit_truncates_with_notice(self) -> None:
        diff   = "a" * 150000
        result = _trim_diff(diff)
        self.assertEqual(len(result), MAX_DIFF_CHARS + len("\n\n[diff truncated for length]"))
        self.assertIn("[diff truncated for length]", result)
        self.assertTrue(result.startswith("a" * MAX_DIFF_CHARS))

    def test_trim_diff_exactly_at_limit_returns_unchanged(self) -> None:
        diff   = "a" * MAX_DIFF_CHARS
        result = _trim_diff(diff)
        self.assertEqual(result, diff)
        self.assertNotIn("[diff truncated for length]", result)

    def test_trim_diff_empty_string_returns_empty(self) -> None:
        result = _trim_diff("")
        self.assertEqual(result, "")

    # ===========================================================
    # Tests for _get_api_key
    # ===========================================================

    def test_get_api_key_present_returns_key(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key-12345"
        }, clear=False):
            result = _get_api_key()
            self.assertEqual(result, "test-key-12345")

    def test_get_api_key_missing_returns_none_and_logs(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("pnp.commit_gen.logger.error") as mock_log:
                result = _get_api_key()
                self.assertIsNone(result)
                mock_log.assert_called_once()
                call_args = mock_log.call_args[0]
                self.assertIn("Missing API key", call_args[0])

    def test_get_api_key_empty_string_returns_empty(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": ""
        }, clear=False):
            result = _get_api_key()
            self.assertEqual(result, "")

    # ===========================================================
    # Tests for _call_openrouter
    # ===========================================================

    def test_call_openrouter_first_model_succeeds(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                mock_response 					= Mock()
                mock_response.status_code 		= 200
                mock_response.json.return_value = SAMPLE_RESPONSE
                mock_post.return_value 			= mock_response

                result = _call_openrouter(SAMPLE_DIFF)

                self.assertIsNotNone(result)
                self.assertIn("feat(api)", result)
                mock_post.assert_called_once()

    def test_call_openrouter_fallback_on_timeout(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                with patch("builtins.print"):
                    # First call times out, second succeeds
                    timeout_error = requests.exceptions.Timeout()
                    mock_success  = Mock()
                    mock_success.status_code 	   = 200
                    mock_success.json.return_value = SAMPLE_RESPONSE

                    mock_post.side_effect = [
                        timeout_error,
                        mock_success
                    ]

                    result = _call_openrouter(SAMPLE_DIFF)

                    self.assertIsNotNone(result)
                    self.assertEqual(mock_post.call_count, 2)

    def test_call_openrouter_fallback_on_rate_limit(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                with patch("builtins.print"):
                    # First call hits rate limit, second succeeds
                    mock_rate_limit			    = Mock()
                    mock_rate_limit.status_code = 429
                    http_error = requests.exceptions.HTTPError(
                      			 response=mock_rate_limit)
                    mock_rate_limit.raise_for_status.side_effect = http_error

                    mock_success 				   = Mock()
                    mock_success.status_code 	   = 200
                    mock_success.json.return_value = SAMPLE_RESPONSE

                    mock_post.side_effect = [
                      mock_rate_limit,
                      mock_success
                    ]

                    result = _call_openrouter(SAMPLE_DIFF)

                    self.assertIsNotNone(result)
                    self.assertEqual(mock_post.call_count, 2)

    def test_call_openrouter_all_models_fail_returns_none(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                with patch("builtins.print"):
                    # All models timeout
                    mock_post.side_effect = requests.exceptions.Timeout()

                    result = _call_openrouter(SAMPLE_DIFF)

                    self.assertIsNone(result)
                    self.assertEqual(mock_post.call_count, len(MODELS))

    def test_call_openrouter_request_structure(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                mock_response 					= Mock()
                mock_response.status_code 		= 200
                mock_response.json.return_value = SAMPLE_RESPONSE
                mock_post.return_value 			= mock_response

                _call_openrouter(SAMPLE_DIFF)

                call_kwargs = mock_post.call_args[1]
                payload 	= json.loads(call_kwargs["data"])

                self.assertEqual(payload["model"], MODELS[0])
                self.assertIn("messages", payload)
                self.assertEqual(len(payload["messages"]), 2)
                self.assertEqual(payload["messages"][0]["role"], "system")
                self.assertEqual(payload["messages"][1]["role"], "user")
                self.assertIn(SAMPLE_DIFF, payload["messages"][1]["content"])
                self.assertEqual(payload["max_tokens"], 10000)
                self.assertEqual(payload["temperature"], 0.2)
                self.assertEqual(payload["reasoning"]["enabled"], False)

    def test_call_openrouter_request_headers(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                mock_response 					= Mock()
                mock_response.status_code 		= 200
                mock_response.json.return_value = SAMPLE_RESPONSE
                mock_post.return_value 			= mock_response

                _call_openrouter(SAMPLE_DIFF)

                call_kwargs = mock_post.call_args[1]
                headers 	= call_kwargs["headers"]

                self.assertEqual(headers["Authorization"], "Bearer test-key")
                self.assertEqual(headers["Content-Type"], "application/json")
                self.assertEqual(headers["HTTP-Referer"], "git-pnp-tool")
                self.assertEqual(headers["X-Title"], "git-pnp-commit-generator")

    def test_call_openrouter_strips_whitespace_from_content(self) -> None:
        with patch.dict(os.environ, {
          "OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                response_with_whitespace = {
                    "choices": [{
                        "message": {
                            "content": "  \n  feat(test): whitespace test  \n  ",
                            "finish_reason": "stop"
                        }
                    }]
                }
                mock_response 					= Mock()
                mock_response.status_code 		= 200
                mock_response.json.return_value = response_with_whitespace
                mock_post.return_value 			= mock_response

                result = _call_openrouter(SAMPLE_DIFF)

                self.assertEqual(result, "feat(test): whitespace test")

    def test_call_openrouter_empty_content_logs_finish_reason(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                with patch("pnp.commit_gen.logger.warning") as mock_log:
                    empty_content_response = {
                        "choices": [{
                            "message": {
                                "content": "",
                                "reasoning": "Some reasoning text here"
                            },
                            "finish_reason": "length"
                        }]
                    }
                    mock_response 					= Mock()
                    mock_response.status_code 		= 200
                    mock_response.json.return_value = empty_content_response
                    mock_post.return_value 			= mock_response

                    result = _call_openrouter(SAMPLE_DIFF)

                    self.assertIsNone(result)
                    mock_log.assert_called()
                    call_args = str(mock_log.call_args)
                    self.assertIn("finish_reason", call_args)

    # ===========================================================
    # Tests for generate_commit_message (public API)
    # ===========================================================

    def test_valid_diff_returns_formatted_message(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                mock_response 					= Mock()
                mock_response.status_code 		= 200
                mock_response.json.return_value = SAMPLE_RESPONSE
                mock_post.return_value 			= mock_response

                result = generate_commit_message(SAMPLE_DIFF)

                self.assertIsNotNone(result)
                self.assertIn("feat(api)", result)

    def test_large_diff_truncates_and_generates_message(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                mock_response 					= Mock()
                mock_response.status_code 		= 200
                mock_response.json.return_value = SAMPLE_RESPONSE
                mock_post.return_value 			= mock_response

                result = generate_commit_message(LARGE_DIFF)

                self.assertIsNotNone(result)
                # Verify the truncated diff was sent
                call_kwargs  = mock_post.call_args[1]
                payload 	 = json.loads(call_kwargs["data"])
                user_content = payload["messages"][1]["content"]
                self.assertIn("[diff truncated for length]", user_content)

    def test_empty_string_diff_returns_none(self) -> None:
        with patch("pnp.commit_gen.logger.warning") as mock_log:
            result = generate_commit_message("")
            self.assertIsNone(result)
            mock_log.assert_called()

    def test_whitespace_only_diff_returns_none(self) -> None:
        with patch("pnp.commit_gen.logger.warning") as mock_log:
            result = generate_commit_message("   \n\t\n   ")
            self.assertIsNone(result)
            mock_log.assert_called()

    def test_response_with_double_quotes_strips_quotes(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                quoted_response = {
                    "choices": [{
                        "message": {
                            "content": '"feat(test): quoted message"',
                            "finish_reason": "stop"
                        }
                    }]
                }
                mock_response 					= Mock()
                mock_response.status_code 		= 200
                mock_response.json.return_value = quoted_response
                mock_post.return_value 			= mock_response

                result = generate_commit_message(SAMPLE_DIFF)

                self.assertEqual(result, "feat(test): quoted message")
                self.assertNotIn('"', result)

    def test_response_with_single_quotes_strips_quotes(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                quoted_response = {
                    "choices": [{
                        "message": {
                            "content": "'feat(test): single quoted message'",
                            "finish_reason": "stop"
                        }
                    }]
                }
                mock_response 					= Mock()
                mock_response.status_code 		= 200
                mock_response.json.return_value = quoted_response
                mock_post.return_value 			= mock_response

                result = generate_commit_message(SAMPLE_DIFF)

                self.assertEqual(result, "feat(test): single quoted message")
                self.assertNotIn("'", result)

    def test_missing_api_key_returns_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("pnp.commit_gen.logger.error"):
                result = generate_commit_message(SAMPLE_DIFF)
                self.assertIsNone(result)

    def test_api_timeout_returns_none_after_all_retries(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                with patch("builtins.print"):
                    mock_post.side_effect = requests.exceptions.Timeout()

                    result = generate_commit_message(SAMPLE_DIFF)

                    self.assertIsNone(result)
                    self.assertEqual(mock_post.call_count, len(MODELS))

    def test_rate_limit_falls_back_to_next_model(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                with patch("builtins.print"):
                    mock_rate_limit 			= Mock()
                    mock_rate_limit.status_code = 429
                    http_error = requests.exceptions.HTTPError(response=mock_rate_limit)
                    mock_rate_limit.raise_for_status.side_effect = http_error

                    mock_success 				   = Mock()
                    mock_success.status_code 	   = 200
                    mock_success.json.return_value = SAMPLE_RESPONSE

                    mock_post.side_effect = [mock_rate_limit, mock_success]

                    result = generate_commit_message(SAMPLE_DIFF)

                    self.assertIsNotNone(result)

    def test_server_error_falls_back_to_next_model(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                with patch("builtins.print"):
                    mock_error 			   = Mock()
                    mock_error.status_code = 500
                    http_error = requests.exceptions.HTTPError(response=mock_error)
                    mock_error.raise_for_status.side_effect = http_error

                    mock_success 				   = Mock()
                    mock_success.status_code 	   = 200
                    mock_success.json.return_value = SAMPLE_RESPONSE

                    mock_post.side_effect = [mock_error, mock_success]

                    result = generate_commit_message(SAMPLE_DIFF)

                    self.assertIsNotNone(result)

    def test_connection_error_returns_none(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                with patch("builtins.print"):
                    mock_post.side_effect = requests.exceptions.ConnectionError()

                    result = generate_commit_message(SAMPLE_DIFF)

                    self.assertIsNone(result)

    def test_invalid_response_format_returns_none(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                with patch("builtins.print"):
                    # Missing "choices" key
                    invalid_response = {"invalid": "structure"}
                    mock_response 					= Mock()
                    mock_response.status_code 		= 200
                    mock_response.json.return_value = invalid_response
                    mock_post.return_value 			= mock_response

                    result = generate_commit_message(SAMPLE_DIFF)

                    self.assertIsNone(result)

    def test_empty_content_returns_none(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                with patch("pnp.commit_gen.logger.warning"):
                    empty_response = {
                        "choices": [{
                            "message": {"content": ""},
                            "finish_reason": "length"
                        }]
                    }
                    mock_response 					= Mock()
                    mock_response.status_code 		= 200
                    mock_response.json.return_value = empty_response
                    mock_post.return_value 			= mock_response

                    result = generate_commit_message(SAMPLE_DIFF)

                    self.assertIsNone(result)

    # ===========================================================
    # Integration and behavior tests
    # ===========================================================

    def test_model_fallback_chain_order(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                with patch("builtins.print"):
                    # All models fail except the last one
                    failures = [
                      requests.exceptions.Timeout()
                      for _ in range(len(MODELS) - 1)
                    ]

                    mock_success 				   = Mock()
                    mock_success.status_code 	   = 200
                    mock_success.json.return_value = SAMPLE_RESPONSE

                    mock_post.side_effect = failures + [mock_success]

                    result = generate_commit_message(SAMPLE_DIFF)

                    self.assertIsNotNone(result)
                    self.assertEqual(mock_post.call_count, len(MODELS))

                    # Verify models were tried in order
                    for i, call in enumerate(mock_post.call_args_list):
                        payload = json.loads(call[1]["data"])
                        self.assertEqual(payload["model"], MODELS[i])

    def test_mixed_failure_types(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                with patch("builtins.print"):
                    # Timeout, then 429, then success
                    mock_timeout = requests.exceptions.Timeout()

                    mock_rate_limit 			= Mock()
                    mock_rate_limit.status_code = 429
                    http_error = requests.exceptions.HTTPError(response=mock_rate_limit)
                    mock_rate_limit.raise_for_status.side_effect = http_error

                    mock_success 				   = Mock()
                    mock_success.status_code 	   = 200
                    mock_success.json.return_value = SAMPLE_RESPONSE

                    mock_post.side_effect = [mock_timeout, mock_rate_limit, mock_success]

                    result = generate_commit_message(SAMPLE_DIFF)

                    self.assertIsNotNone(result)
                    self.assertEqual(mock_post.call_count, 3)

    def test_finally_block_returns_content_early(self) -> None:
        with patch.dict(os.environ, {
          	"OPENROUTER_API_KEY": "test-key"
        }, clear=False):
            with patch("pnp.commit_gen.requests.post") as mock_post:
                with patch("builtins.print") as mock_print:
                    # Success on first try
                    mock_response 					= Mock()
                    mock_response.status_code 		= 200
                    mock_response.json.return_value = SAMPLE_RESPONSE
                    mock_post.return_value 			= mock_response

                    result = _call_openrouter(SAMPLE_DIFF)

                    self.assertIsNotNone(result)
                    # Print should not be called since we succeeded on first model
                    mock_print.assert_not_called()
                    # Only one model should be tried
                    mock_post.assert_called_once()


if __name__ == "__main__": unittest.main()
