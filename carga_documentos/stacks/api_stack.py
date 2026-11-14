"""API Stack — carga_documentos (REST API OpenAPI-driven + Cognito authorizer).

Crea la Lambda `hello` (ping a Aurora por Data API) y la API REST a partir de
`api/openapi.yaml` (SpecRestApi), con Cognito User Pool Authorizer, CORS y
throttling a nivel de stage.

Consume por SSM: User Pool ARN (outhenticator) y cluster ARN / secret ARN /
nombre de base (database). Publica la URL de la API en SSM.
"""
from pathlib import Path
from typing import Any, Dict

import yaml
from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    Tags,
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_ssm as ssm,
)
from constructs import Construct

from configs.env_resolver import prefixed_name, removal_config, ssm_param_name

COMPONENT = "api-carga"


class ApiStack(Stack):
    """Lambda hello + REST API desde OpenAPI + Cognito authorizer + throttling."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        env_name: str,
        config: dict,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        api_cfg = config["api"]
        cors_origins = api_cfg["cors_allow_origins"]
        throttling = api_cfg["throttling"]

        # ── Valores desde SSM (de otros repos) ─────────────────────────────
        user_pool_arn = ssm.StringParameter.value_for_string_parameter(
            self, ssm_param_name(env_name, "cognito", "user-pool-arn")
        )
        cluster_arn = ssm.StringParameter.value_for_string_parameter(
            self, ssm_param_name(env_name, "database", "cluster-arn")
        )
        secret_arn = ssm.StringParameter.value_for_string_parameter(
            self, ssm_param_name(env_name, "database", "master-secret-arn")
        )
        db_name = ssm.StringParameter.value_for_string_parameter(
            self, ssm_param_name(env_name, "database", "db-name")
        )

        # ── Lambda hello ───────────────────────────────────────────────────
        fn_name = prefixed_name(env_name, "Unipaz-Carga-Hello")
        log_group = logs.LogGroup(
            self,
            "HelloFnLogs",
            log_group_name=f"/aws/lambda/{fn_name}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=removal_config(env_name),
        )
        fn = lambda_.Function(
            self,
            "HelloFn",
            function_name=fn_name,
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                "source/lambda/hello",
                exclude=["__pycache__", "*.pyc", "test_*.py"],
            ),
            timeout=Duration.seconds(int(api_cfg["timeout_seconds"])),
            memory_size=int(api_cfg["memory_mb"]),
            log_group=log_group,
            environment={
                "CLUSTER_ARN": cluster_arn,
                "SECRET_ARN": secret_arn,
                "DB_NAME": db_name,
                "CORS_ORIGINS": ",".join(cors_origins),
            },
        )

        # IAM: Data API sobre el cluster + lectura del secreto master.
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement"],
                resources=[cluster_arn],
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[secret_arn],
            )
        )

        # ── REST API desde la spec OpenAPI ─────────────────────────────────
        api = apigw.SpecRestApi(
            self,
            "RestApi",
            rest_api_name=prefixed_name(env_name, "Unipaz-Carga-Api"),
            api_definition=apigw.ApiDefinition.from_inline(
                self._load_openapi(
                    region=self.region,
                    lambda_arn=fn.function_arn,
                    user_pool_arn=user_pool_arn,
                )
            ),
            # Evita crear el AWS::ApiGateway::Account (singleton de la cuenta).
            cloud_watch_role=False,
            deploy_options=apigw.StageOptions(
                stage_name=env_name,
                throttling_rate_limit=float(throttling["rate_limit"]),
                throttling_burst_limit=int(throttling["burst_limit"]),
            ),
        )

        fn.add_permission(
            "ApiGatewayInvoke",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            source_arn=api.arn_for_execute_api(),
        )

        # ── Publicar URL de la API en SSM ──────────────────────────────────
        ssm.StringParameter(
            self,
            "ApiUrlParam",
            parameter_name=ssm_param_name(env_name, COMPONENT, "url"),
            string_value=api.url,
        )

        Tags.of(self).add("component", COMPONENT)
        CfnOutput(self, "ApiUrl", value=api.url)

    def _load_openapi(self, region: str, lambda_arn: str, user_pool_arn: str) -> Dict[str, Any]:
        """Carga api/openapi.yaml y resuelve los placeholders ${...}.

        Los ARN llegan como tokens de CDK; al insertarlos por reemplazo de
        string, CDK los resuelve al sintetizar `from_inline`.
        """
        spec_path = Path(__file__).resolve().parent.parent / "api" / "openapi.yaml"
        raw = spec_path.read_text(encoding="utf-8")
        raw = raw.replace("${region}", region)
        raw = raw.replace("${lambda_arn}", lambda_arn)
        raw = raw.replace("${user_pool_arn}", user_pool_arn)
        return yaml.safe_load(raw)
