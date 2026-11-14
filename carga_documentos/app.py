"""CDK App — API carga_documentos (Repositorio Digital UNIPAZ).

API REST protegida con Cognito. Consume por SSM los outputs de `outhenticator`
(User Pool ARN) y `database` (Aurora Data API). Publica su URL en SSM.

Cadena en cdk.json: `python validate_env.py && python app.py`.
"""
import aws_cdk as cdk

from configs.config import load_config
from configs.env_resolver import prefixed_name, read_env
from stacks.api_stack import ApiStack


app = cdk.App()

env_name = read_env()
app_config = load_config("app_config.yaml")
api_config = load_config("api.yaml")
app_settings = app_config["app_settings"]

env = cdk.Environment(
    account=app_settings["account_id"],
    region=app_settings["region"],
)

cdk.Tags.of(app).add("project", "Unipaz")
cdk.Tags.of(app).add("environment", env_name)
for key, value in app_settings.get("tags", {}).items():
    cdk.Tags.of(app).add(key, value)

ApiStack(
    app,
    prefixed_name(env_name, "Unipaz-Carga-Api"),
    env_name=env_name,
    config=api_config,
    env=env,
    description="REST API (Cognito) carga_documentos - Repositorio UNIPAZ",
)

app.synth()
