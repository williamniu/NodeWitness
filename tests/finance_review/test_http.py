"""Run against the local production preview on port 3016. No model calls."""

import http.cookiejar
import http.client
import json
import unittest
import urllib.error
import urllib.request

from finance_runtime.sources import ROOT

URL = "http://127.0.0.1:3016"


class HttpBoundary(unittest.TestCase):
    def test_local_origin_token_host_and_path_boundaries(self):
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        state = json.load(opener.open(URL + "/api/finance"))
        checks = {}
        for label, headers, route, method, body, status in (
            ("missing_token", {"Origin": URL}, "/api/finance", "POST", b'{"operation":"start"}', 403),
            ("foreign_origin", {"Origin": "https://example.invalid", "x-nw-local-token": state["csrf"]}, "/api/finance", "POST", b'{"operation":"start"}', 403),
            ("host_rebinding", {"Host": "example.invalid"}, "/api/finance", "GET", None, 403),
            ("no_general_command", {"Origin": URL, "x-nw-local-token": state["csrf"]}, "/api/finance", "POST", b'{"operation":"shell","payload":{"command":"echo blocked"}}', 409),
            ("source_path_escape", {}, "/api/finance?source=../../README.md&record_id=x", "GET", None, 400),
        ):
            if label == "host_rebinding":
                connection = http.client.HTTPConnection("127.0.0.1", 3016)
                connection.request(method, route, headers=headers)
                response = connection.getresponse()
                self.assertEqual(response.status, status, label)
                response.read()
                connection.close()
                checks[label] = status
                continue
            request = urllib.request.Request(URL + route, data=body, headers=headers, method=method)
            with self.assertRaises(urllib.error.HTTPError, msg=label) as error:
                opener.open(request)
            self.assertEqual(error.exception.code, status, label)
            checks[label] = error.exception.code
        after = json.load(opener.open(URL + "/api/finance"))
        self.assertEqual(state["head"], after["head"])
        (ROOT / "outputs/nw003/http-boundary.json").write_text(json.dumps({"checks": checks, "head_unchanged": True}, indent=2) + "\n")


if __name__ == "__main__":
    unittest.main()
