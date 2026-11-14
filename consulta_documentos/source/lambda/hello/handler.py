"""Lambda hello (consulta_documentos) — GET /hello.

Hola mundo PÚBLICO (sin Cognito): hace un ping a Aurora (Data API) para
comprobar la integración UI -> API -> Aurora.

Respuestas:
  200 con mensaje + info de la base.
  503 si Aurora se está reanudando (auto-pause), la UI debe reintentar.
  500 con formato de error estándar ante otros fallos.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

import db

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SERVICE = "consulta_documentos"
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()
]


def _resolve_origin(event: Dict[str, Any]) -> str:
    """Refleja el Origin si está permitido; si no, el primero de la lista."""
    headers = event.get("headers") or {}
    origin = headers.get("origin") or headers.get("Origin")
    if ALLOWED_ORIGINS == ["*"]:
        return "*"
    if origin and origin in ALLOWED_ORIGINS:
        return origin
    return ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*"


def _cors_headers(origin: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET,OPTIONS",
    }


def _response(status: int, body: Dict[str, Any], origin: str) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": _cors_headers(origin),
        "body": json.dumps(body),
    }


def _error(status: int, code: str, message: str, origin: str) -> Dict[str, Any]:
    return _response(status, {"error": {"code": code, "message": message}}, origin)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    origin = _resolve_origin(event)

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": _cors_headers(origin), "body": ""}

    try:
        database = db.ping()
    except db.DatabaseResumingError:
        logger.warning("database_resuming")
        return _error(
            503, "DATABASE_RESUMING",
            "La base de datos se está iniciando, intenta de nuevo en unos segundos",
            origin,
        )
    except Exception:  # noqa: BLE001
        logger.exception("database_ping_failed")
        return _error(500, "INTERNAL_ERROR", "No se pudo consultar la base de datos", origin)

    logger.info("hello_served")
    return _response(
        200,
        {
            "message": "Hola mundo desde consulta_documentos",
            "service": SERVICE,
            "database": database,
        },
        origin,
    )
