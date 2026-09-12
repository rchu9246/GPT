import json
import os
import traceback
import unittest
from unittest.mock import patch

import requests

from automation.enterprise2.client import SupabaseRestClient


class ClientDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
            "OTHER_SECRET": "another-private-value",
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = SupabaseRestClient()

    def response(self, status, body):
        response = requests.Response()
        response.status_code = status
        response._content = body.encode()
        response.encoding = "utf-8"
        response.url = self.client.url + "/rest/v1/quant_events?secret=hidden-query"
        response.request = requests.Request("POST", response.url).prepare()
        return response

    def cases(self):
        payload = {"symbol": "2330"}
        headers = self.client.headers
        return [
            ("get", ("quant_events", "select=*"), "get", "?select=*", headers, None),
            ("insert", ("quant_events", payload), "post", "",
             {**headers, "Prefer": "return=representation"}, payload),
            ("upsert", ("quant_events", payload, "account_name,symbol"), "post",
             "?on_conflict=account_name%2Csymbol",
             {**headers, "Prefer": "resolution=merge-duplicates,return=representation"}, payload),
            ("patch", ("quant_events", "id=eq.1", payload), "patch", "?id=eq.1",
             {**headers, "Prefer": "return=representation"}, payload),
        ]

    def test_success_preserves_requests_and_return_values(self):
        for method, args, verb, query, headers, payload in self.cases():
            with self.subTest(method=method), patch(
                "automation.enterprise2.client.requests." + verb,
                return_value=self.response(200, '[{"id": 1}]'),
            ) as send:
                self.assertEqual(getattr(self.client, method)(*args), [{"id": 1}])
                expected = {"headers": headers, "timeout": 45}
                if payload is not None:
                    expected["json"] = payload
                send.assert_called_once_with(
                    self.client.url + "/rest/v1/quant_events" + query, **expected
                )

    def test_all_http_failures_include_diagnostics(self):
        body = json.dumps({"code": "42P10", "message": "No matching unique constraint",
                           "details": None, "hint": None})
        for method, args, verb, *_ in self.cases():
            for status in (400, 401, 403, 409, 500):
                with self.subTest(method=method, status=status):
                    response = self.response(status, body)
                    with patch("automation.enterprise2.client.requests." + verb,
                               return_value=response), self.assertRaises(requests.HTTPError) as caught:
                        getattr(self.client, method)(*args)
                    self.assertIn(f"HTTP {status} {verb.upper()} /rest/v1/quant_events", str(caught.exception))
                    self.assertIn(body, str(caught.exception))
                    self.assertIs(caught.exception.response, response)
                    self.assertIs(caught.exception.request, response.request)

    def test_redacts_secrets_in_body_and_traceback(self):
        body = ('test-service-key another-private-value '
                'Bearer unknown-credential {"apikey":"unknown-api-key"} '
                'sb_secret_example eyJexample.payload.signature '
                'https://someone:password@example.invalid/path?token=private')
        response = self.response(400, body)
        table = "quant_events?secret=path-secret"
        with patch("automation.enterprise2.client.requests.get", return_value=response):
            try:
                self.client.get(table)
            except requests.HTTPError:
                rendered = traceback.format_exc()
            else:
                self.fail("Expected HTTPError")
        for private in ("test-service-key", "another-private-value", "unknown-credential",
                        "unknown-api-key", "sb_secret_example", "eyJexample.payload.signature",
                        "example.invalid", "example.supabase.co", "hidden-query", "path-secret"):
            self.assertNotIn(private, rendered)
        self.assertIn("HTTP 400 GET /rest/v1/[redacted]", rendered)

    def test_plain_text_error_body(self):
        with patch("automation.enterprise2.client.requests.get",
                   return_value=self.response(502, "upstream unavailable")):
            with self.assertRaisesRegex(requests.HTTPError, "upstream unavailable"):
                self.client.get("quant_events")

    def test_transport_errors_are_unchanged(self):
        error = requests.Timeout("timed out")
        with patch("automation.enterprise2.client.requests.get", side_effect=error):
            with self.assertRaises(requests.Timeout) as caught:
                self.client.get("quant_events")
        self.assertIs(caught.exception, error)


if __name__ == "__main__":
    unittest.main()
