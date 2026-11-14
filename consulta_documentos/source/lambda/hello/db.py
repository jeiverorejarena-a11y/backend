"""Acceso a Aurora PostgreSQL vía RDS Data API (HTTPS, sin VPC ni driver).

Config por variables de entorno: CLUSTER_ARN, SECRET_ARN, DB_NAME.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import boto3

_client: Optional[Any] = None


class DatabaseResumingError(Exception):
    """Aurora Serverless v2 está saliendo de auto-pause; reintentar en segundos."""


def _rds_data():
    global _client
    if _client is None:
        _client = boto3.client("rds-data")
    return _client


def ping() -> Dict[str, str]:
    """Consulta mínima para validar la conexión: base, hora del servidor y versión."""
    try:
        result = _rds_data().execute_statement(
            resourceArn=os.environ["CLUSTER_ARN"],
            secretArn=os.environ["SECRET_ARN"],
            database=os.environ["DB_NAME"],
            sql="SELECT current_database(), now()::text, version()",
        )
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if code == "DatabaseResumingException":
            raise DatabaseResumingError() from exc
        raise

    row = result["records"][0]
    return {
        "name": row[0]["stringValue"],
        "server_time": row[1]["stringValue"],
        "version": row[2]["stringValue"],
    }
