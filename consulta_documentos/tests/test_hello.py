"""Tests de la Lambda hello (consulta_documentos).

Ejecutar desde backend/consulta_documentos:
    python -m unittest discover -s tests -v

boto3 se stubea en sys.modules, así que no hace falta instalarlo ni tener
credenciales AWS.
"""
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

LAMBDA_DIR = Path(__file__).resolve().parent.parent / "source" / "lambda" / "hello"
sys.path.insert(0, str(LAMBDA_DIR))
sys.modules.setdefault("boto3", types.SimpleNamespace(client=lambda *_a, **_k: None))
os.environ.update(CLUSTER_ARN="arn:cluster", SECRET_ARN="arn:secret", DB_NAME="testdb")

import db  # noqa: E402
import handler  # noqa: E402


class _ClientError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


def _event(method="GET"):
    return {"httpMethod": method, "headers": {"origin": "http://localhost:5173"}}


class HelloHandlerTest(unittest.TestCase):
    def setUp(self):
        self.fake_client = mock.Mock()
        db._client = self.fake_client

    def test_ok_without_auth(self):
        self.fake_client.execute_statement.return_value = {
            "records": [[
                {"stringValue": "testdb"},
                {"stringValue": "2026-01-01 00:00:00+00"},
                {"stringValue": "PostgreSQL 17.5"},
            ]]
        }
        res = handler.handler(_event(), None)

        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertEqual(body["service"], "consulta_documentos")
        self.assertNotIn("user", body)
        self.assertEqual(body["database"]["version"], "PostgreSQL 17.5")

    def test_database_resuming_returns_503(self):
        self.fake_client.execute_statement.side_effect = _ClientError("DatabaseResumingException")
        res = handler.handler(_event(), None)
        self.assertEqual(res["statusCode"], 503)

    def test_other_errors_return_500(self):
        self.fake_client.execute_statement.side_effect = RuntimeError("boom")
        res = handler.handler(_event(), None)
        self.assertEqual(res["statusCode"], 500)
        self.assertNotIn("boom", res["body"])

    def test_options_preflight_skips_database(self):
        res = handler.handler(_event(method="OPTIONS"), None)
        self.assertEqual(res["statusCode"], 200)
        self.fake_client.execute_statement.assert_not_called()


if __name__ == "__main__":
    unittest.main()
