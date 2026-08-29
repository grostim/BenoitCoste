"""Offline tests for credential-isolated GrampsWeb URL handling."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from scripts.gramps_api import GrampsApiClient


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps({"access_token": "test-token"}).encode("utf-8")


class GrampsApiUrlTests(unittest.TestCase):
    @patch("scripts.gramps_api.urlopen")
    def test_login_uses_https_trailing_slash_endpoint(self, urlopen):
        urlopen.return_value = _Response()
        client = GrampsApiClient(
            "https://example.invalid/api/",
            "test-user",
            "test-password",
        )

        client._login()

        request = urlopen.call_args.args[0]
        assert request.full_url == "https://example.invalid/api/token/"
        assert client._token == "test-token"
