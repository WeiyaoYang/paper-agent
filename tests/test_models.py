import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from paper_agent.models.client import ModelError, generate_text


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = self.root / ".env.local"
        self.env.write_text("OPENAI_API_KEY=test-only-not-real\n", encoding="utf-8")
        self.log = self.root / "usage.jsonl"

    def call(self):
        return generate_text("private example prompt", "test instructions", env_file=self.env, usage_path=self.log)

    def test_missing_key_does_not_send_request(self):
        self.env.write_text("OPENAI_API_KEY=\n", encoding="utf-8")
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), patch("openai.OpenAI") as factory:
            with self.assertRaises(ModelError) as caught:
                self.call()
            self.assertEqual("missing_api_key", caught.exception.code)
            factory.assert_not_called()

    def test_success_logs_usage_not_key_or_content(self):
        usage = {"input_tokens": 12, "output_tokens": 8,
                 "output_tokens_details": {"reasoning_tokens": 3}}
        response = SimpleNamespace(id="resp_test", model="test-model", status="completed",
                                   output_text="test answer", usage=SimpleNamespace(model_dump=lambda: usage))
        with patch("openai.OpenAI") as factory:
            create = factory.return_value.__enter__.return_value.responses.create
            create.return_value = response
            result = self.call()
            self.assertEqual("test answer", result["text"])
            self.assertFalse(create.call_args.kwargs["store"])
            self.assertEqual(0, factory.call_args.kwargs["max_retries"])
            self.assertEqual("https://api.openai.com/v1", factory.call_args.kwargs["base_url"])
        log = self.log.read_text(encoding="utf-8")
        self.assertEqual(3, json.loads(log)["usage"]["output_tokens_details"]["reasoning_tokens"])
        for private in ("test-only-not-real", "private example prompt", "test answer"):
            self.assertNotIn(private, log)

    def test_tool_response_preserves_items_and_request_options(self):
        item = SimpleNamespace(model_dump=lambda **kw: {"type": "reasoning", "encrypted_content": "opaque"})
        response = SimpleNamespace(id="resp_test", model="test-model", status="completed",
                                   output_text="", usage=None, output=[item, SimpleNamespace(model_dump=lambda **kw: {"type": "function_call", "name": "read", "arguments": "{}", "call_id": "test"})])
        with patch("openai.OpenAI") as factory:
            create = factory.return_value.__enter__.return_value.responses.create
            create.return_value = response
            result = generate_text([{"role": "user", "content": "task"}], "policy", tools=[],
                                   env_file=self.env, usage_path=self.log)
            self.assertEqual("reasoning", result["output"][0]["type"])
            self.assertNotIn("warning", result)
            self.assertFalse(create.call_args.kwargs["parallel_tool_calls"])
            self.assertIn("reasoning.encrypted_content", create.call_args.kwargs["include"])
            self.assertEqual("policy", create.call_args.kwargs["instructions"])

    def test_authentication_error_is_sanitized(self):
        from openai import APIStatusError

        response = MagicMock(status_code=401)
        error = APIStatusError("echoing test-only-not-real", response=response, body=None)
        with patch("openai.OpenAI") as factory:
            create = factory.return_value.__enter__.return_value.responses.create
            create.side_effect = error
            with self.assertRaises(ModelError) as caught:
                self.call()
            self.assertEqual("authentication_failed", caught.exception.code)
            self.assertNotIn("test-only-not-real", str(caught.exception))
            self.assertEqual(1, create.call_count)
        self.assertNotIn("test-only-not-real", self.log.read_text(encoding="utf-8"))

    def test_incomplete_response_keeps_usage_and_does_not_retry(self):
        response = SimpleNamespace(id="resp_test", model="test-model", status="incomplete",
                                   output_text="", usage=SimpleNamespace(model_dump=lambda: {"output_tokens": 1024}))
        with patch("openai.OpenAI") as factory:
            create = factory.return_value.__enter__.return_value.responses.create
            create.return_value = response
            result = self.call()
            self.assertIn("warning", result)
            self.assertEqual(1024, result["usage"]["output_tokens"])
            self.assertEqual(1, create.call_count)
