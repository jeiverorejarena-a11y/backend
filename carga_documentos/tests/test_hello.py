"""Tests de la Lambda hello (carga_documentos).

Ejecutar desde backend/carga_documentos:
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


def _event(method="GET", claims=None):
    return {
        "httpMethod": method,
        "headers": {"origin": "http://localhost:5173"},
        "requestContext": {"authorizer": {"claims": claims or {}}},
    }


class HelloHandlerTest(unittest.TestCase):
    def setUp(self):
        self.fake_client = mock.Mock()
        db._client = self.fake_client

    def test_ok_returns_user_and_database(self):
        self.fake_client.execute_statement.return_value = {
            "records": [[
                {"stringValue": "testdb"},
                {"stringValue": "2026-01-01 00:00:00+00"},
                {"stringValue": "PostgreSQL 17.5"},
            ]]
        }
        res = handler.handler(_event(claims={"email": "a@unipaz.edu.co", "sub": "123"}), None)

        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertEqual(body["service"], "carga_documentos")
        self.assertEqual(body["user"], {"email": "a@unipaz.edu.co", "sub": "123"})
        self.assertEqual(body["database"]["name"], "testdb")
        kwargs = self.fake_client.execute_statement.call_args.kwargs
        self.assertEqual(kwargs["resourceArn"], "arn:cluster")
        self.assertEqual(kwargs["secretArn"], "arn:secret")

    def test_database_resuming_returns_503(self):
        self.fake_client.execute_statement.side_effect = _ClientError("DatabaseResumingException")
        res = handler.handler(_event(), None)
        self.assertEqual(res["statusCode"], 503)
        self.assertEqual(json.loads(res["body"])["error"]["code"], "DATABASE_RESUMING")

    def test_other_errors_return_500_without_details(self):
        self.fake_client.execute_statement.side_effect = _ClientError("BadRequestException")
        res = handler.handler(_event(), None)
        self.assertEqual(res["statusCode"], 500)
        self.assertNotIn("BadRequestException", res["body"])

    def test_options_preflight_skips_database(self):
        res = handler.handler(_event(method="OPTIONS"), None)
        self.assertEqual(res["statusCode"], 200)
        self.assertIn("Access-Control-Allow-Origin", res["headers"])
        self.fake_client.execute_statement.assert_not_called()


if __name__ == "__main__":
    unittest.main()
