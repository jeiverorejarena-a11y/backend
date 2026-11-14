"""Tests del ApiStack de consulta_documentos (CDK assertions).

Ejecutar desde la raíz del repo:
    python -m unittest discover -s tests -v
"""
import json
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import aws_cdk as cdk  # noqa: E402
from aws_cdk.assertions import Match, Template  # noqa: E402

from stacks.api_stack import ApiStack  # noqa: E402

ENV = cdk.Environment(account="041391475423", region="us-east-2")


def _synth():
    cfg = yaml.safe_load((ROOT / "configs" / "api.yaml").read_text(encoding="utf-8"))
    app = cdk.App()
    stack = ApiStack(app, "TestConsultaApi", env_name="prod", config=cfg, env=ENV)
    return app, Template.from_stack(stack)


class ConsultaApiStackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.t = _synth()
        cls.body = next(
            r["Properties"]["Body"]
            for r in cls.t.to_json()["Resources"].values()
            if r["Type"] == "AWS::ApiGateway::RestApi"
        )

    def test_hello_is_public(self):
        self.assertNotIn("security", self.body["paths"]["/hello"]["get"])
        self.assertNotIn("securitySchemes", self.body.get("components", {}))

    def test_no_cognito_dependency(self):
        params = self.t.find_parameters(
            "*", {"Default": "/unipaz/prod/repositorio/cognito/user-pool-arn"}
        )
        self.assertEqual(params, {})

    def test_gateway_responses_have_cors(self):
        gr = self.body["x-amazon-apigateway-gateway-responses"]
        for key in ("DEFAULT_4XX", "DEFAULT_5XX"):
            self.assertIn(
                "gatewayresponse.header.Access-Control-Allow-Origin",
                gr[key]["responseParameters"],
            )

    def test_stage_throttling_5_tps(self):
        self.t.has_resource_properties(
            "AWS::ApiGateway::Stage",
            {
                "StageName": "prod",
                "MethodSettings": Match.array_with(
                    [Match.object_like({"ThrottlingRateLimit": 5, "ThrottlingBurstLimit": 5})]
                ),
            },
        )

    def test_lambda_python_arm(self):
        self.t.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "FunctionName": "prod-Unipaz-Consulta-Hello",
                "Runtime": "python3.12",
                "Architectures": ["arm64"],
            },
        )

    def test_reads_database_from_ssm(self):
        for name in (
            "/unipaz/prod/repositorio/database/cluster-arn",
            "/unipaz/prod/repositorio/database/master-secret-arn",
            "/unipaz/prod/repositorio/database/db-name",
        ):
            self.assertEqual(len(self.t.find_parameters("*", {"Default": name})), 1, name)

    def test_publishes_url(self):
        self.t.has_resource_properties(
            "AWS::SSM::Parameter", {"Name": "/unipaz/prod/repositorio/api-consulta/url"}
        )

    def test_no_context_lookups(self):
        manifest = json.loads(
            (Path(self.app.synth().directory) / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual([m["key"] for m in manifest.get("missing", [])], [])


if __name__ == "__main__":
    unittest.main()
