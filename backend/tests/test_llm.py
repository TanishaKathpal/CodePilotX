import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.llm.client import (AnthropicClient, LLMError, OpenAICompatibleClient, extract_json, get_llm)
from app.llm.schemas import parse_diagnosis, parse_fix
from tests.helpers import make_settings


class MockServer:
    """Local HTTP server that mimics the *documented* response shapes of the two APIs.
    This verifies our request/response handling, NOT that a real provider accepts our request."""

    def __init__(self, script):
        self.script = list(script)  # list of (status, body_dict)
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("content-length", 0))
                outer.requests.append({"path": self.path, "headers": dict(self.headers),
                                       "body": json.loads(self.rfile.read(n))})
                status, body = outer.script.pop(0) if outer.script else (500, {"error": "script empty"})
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


ANTH_OK = {"content": [{"type": "text", "text": '{"a": 1}'}], "stop_reason": "end_turn"}


class AnthropicClientTests(unittest.TestCase):
    def test_request_shape_and_parse(self):
        srv = MockServer([(200, ANTH_OK)])
        self.addCleanup(srv.close)
        s = make_settings(anthropic_api_key="sk-test", anthropic_base_url=srv.url, llm_model="m-1",
                          llm_max_tokens=77)
        out = AnthropicClient(s, sleep=lambda _: None).complete("SYS", "USER")
        self.assertEqual(out, '{"a": 1}')
        r = srv.requests[0]
        self.assertEqual(r["path"], "/v1/messages")
        self.assertEqual(r["headers"]["x-api-key"], "sk-test")
        self.assertEqual(r["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(r["body"]["model"], "m-1")
        self.assertEqual(r["body"]["max_tokens"], 77)
        self.assertEqual(r["body"]["system"], "SYS")
        self.assertEqual(r["body"]["messages"], [{"role": "user", "content": "USER"}])
        self.assertNotIn("temperature", r["body"])

    def test_temperature_only_when_configured(self):
        srv = MockServer([(200, ANTH_OK)])
        self.addCleanup(srv.close)
        s = make_settings(anthropic_api_key="k", anthropic_base_url=srv.url, llm_temperature=0.0)
        AnthropicClient(s).complete("s", "u")
        self.assertEqual(srv.requests[0]["body"]["temperature"], 0.0)

    def test_retries_on_overload_then_succeeds(self):
        srv = MockServer([(529, {"error": {"message": "overloaded"}}), (429, {"error": {"message": "slow"}}),
                          (200, ANTH_OK)])
        self.addCleanup(srv.close)
        sleeps = []
        s = make_settings(anthropic_api_key="k", anthropic_base_url=srv.url)
        out = AnthropicClient(s, sleep=sleeps.append).complete("s", "u")
        self.assertEqual(out, '{"a": 1}')
        self.assertEqual(len(srv.requests), 3)
        self.assertEqual(sleeps, [1, 2])

    def test_gives_up_after_retries(self):
        srv = MockServer([(500, {"error": "x"})] * 5)
        self.addCleanup(srv.close)
        s = make_settings(anthropic_api_key="k", anthropic_base_url=srv.url)
        with self.assertRaises(LLMError) as cm:
            AnthropicClient(s, sleep=lambda _: None, max_retries=2).complete("s", "u")
        self.assertIn("3 attempts", str(cm.exception))

    def test_auth_error_not_retried_and_key_not_leaked(self):
        srv = MockServer([(401, {"error": {"message": "invalid x-api-key"}})])
        self.addCleanup(srv.close)
        s = make_settings(anthropic_api_key="sk-SECRET", anthropic_base_url=srv.url)
        with self.assertRaises(LLMError) as cm:
            AnthropicClient(s, sleep=lambda _: None).complete("s", "u")
        self.assertEqual(len(srv.requests), 1)
        self.assertIn("API key", str(cm.exception))
        self.assertNotIn("sk-SECRET", str(cm.exception))

    def test_bad_model_404_message(self):
        srv = MockServer([(404, {"error": {"message": "model: nope"}})])
        self.addCleanup(srv.close)
        s = make_settings(anthropic_api_key="k", anthropic_base_url=srv.url)
        with self.assertRaises(LLMError) as cm:
            AnthropicClient(s).complete("s", "u")
        self.assertIn("LLM_MODEL", str(cm.exception))

    def test_malformed_success_body(self):
        srv = MockServer([(200, {"unexpected": True})])
        self.addCleanup(srv.close)
        s = make_settings(anthropic_api_key="k", anthropic_base_url=srv.url)
        with self.assertRaises(LLMError):
            AnthropicClient(s).complete("s", "u")

    def test_connection_refused_is_llm_error(self):
        s = make_settings(anthropic_api_key="k", anthropic_base_url="http://127.0.0.1:1", llm_timeout_s=2)
        with self.assertRaises(LLMError) as cm:
            AnthropicClient(s, sleep=lambda _: None, max_retries=1).complete("s", "u")
        self.assertIn("network error", str(cm.exception))


class OpenAIClientTests(unittest.TestCase):
    def test_request_and_parse(self):
        srv = MockServer([(200, {"choices": [{"message": {"content": "hello"}}]})])
        self.addCleanup(srv.close)
        s = make_settings(llm_provider="openai_compatible", openai_api_key="ok", openai_base_url=srv.url,
                          llm_model="gpt-x")
        self.assertEqual(OpenAICompatibleClient(s).complete("SYS", "USER"), "hello")
        r = srv.requests[0]
        self.assertEqual(r["path"], "/chat/completions")
        self.assertEqual(r["headers"]["authorization"], "Bearer ok")
        self.assertEqual(r["body"]["messages"][0], {"role": "system", "content": "SYS"})


class FactoryTests(unittest.TestCase):
    def test_no_key_means_none(self):
        self.assertIsNone(get_llm(make_settings()))
        self.assertIsNone(get_llm(make_settings(llm_provider="openai_compatible")))

    def test_with_keys(self):
        self.assertIsInstance(get_llm(make_settings(anthropic_api_key="k")), AnthropicClient)
        self.assertIsInstance(get_llm(make_settings(llm_provider="openai_compatible", openai_api_key="k")),
                              OpenAICompatibleClient)

    def test_local_openai_compatible_needs_no_key(self):
        s = make_settings(llm_provider="openai_compatible", openai_base_url="http://localhost:11434/v1")
        self.assertIsInstance(get_llm(s), OpenAICompatibleClient)

    def test_unknown_provider(self):
        with self.assertRaises(ValueError):
            get_llm(make_settings(llm_provider="nope"))


class ExtractJsonTests(unittest.TestCase):
    def test_variants(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(extract_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(extract_json('Sure! Here:\n{"a": {"b": "}"}} hope that helps'), {"a": {"b": "}"}})
        self.assertEqual(extract_json('{"code": "def f():\\n    return \\"x\\""}'), {"code": 'def f():\n    return "x"'})

    def test_failures(self):
        for bad in ["", "no json here", "[1,2]", '{"a": ']:
            with self.assertRaises(LLMError):
                extract_json(bad)


class SchemaTests(unittest.TestCase):
    GOOD_DIAG = {"summary": "s", "root_cause": "r", "confidence": "HIGH",
                 "suspects": [{"file": "./a/b.py", "symbol": "f", "reason": "x", "chunk_ids": ["C1"]},
                              {"file": "ghost.py", "symbol": "g"}]}

    def test_diagnosis_grounding(self):
        d = parse_diagnosis(self.GOOD_DIAG, {"a/b.py"})
        self.assertEqual(d["confidence"], "high")
        self.assertTrue(d["suspects"][0]["verified"])
        self.assertEqual(d["suspects"][0]["file"], "a/b.py")
        self.assertFalse(d["suspects"][1]["verified"])  # hallucinated file flagged

    def test_diagnosis_errors(self):
        with self.assertRaises(LLMError):
            parse_diagnosis({"summary": "s", "root_cause": "r", "suspects": []}, set())
        with self.assertRaises(LLMError):
            parse_diagnosis({"root_cause": "r", "suspects": [{}]}, set())
        d = parse_diagnosis({**self.GOOD_DIAG, "confidence": "certain"}, set())
        self.assertEqual(d["confidence"], "low")

    GOOD_FIX = {"explanation": "e", "edits": [{"file": "a.py", "search": "x", "replace": "y"}],
                "test_code": "def test_a():\n    assert 1\n", "test_rationale": "r"}

    def test_fix_ok(self):
        self.assertEqual(parse_fix(self.GOOD_FIX)["edits"][0]["replace"], "y")

    def test_fix_rejections(self):
        cases = [
            {**self.GOOD_FIX, "edits": []},
            {**self.GOOD_FIX, "edits": [{"file": "a.py", "search": "x", "replace": "y"}] * 4},
            {**self.GOOD_FIX, "edits": [{"file": "a.py", "search": "", "replace": "y"}]},
            {**self.GOOD_FIX, "edits": [{"file": "a.py", "search": "x"}]},
            {**self.GOOD_FIX, "edits": ["nope"]},
            {**self.GOOD_FIX, "test_code": "print('no tests')"},
            {**self.GOOD_FIX, "test_code": "def test_x():\n    pass\n" + "#" * 25000},
            {k: v for k, v in self.GOOD_FIX.items() if k != "explanation"},
        ]
        for c in cases:
            with self.assertRaises(LLMError, msg=str(c)[:80]):
                parse_fix(c)


if __name__ == "__main__":
    unittest.main()
