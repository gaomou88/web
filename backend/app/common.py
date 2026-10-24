from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def raw_json(data: bytes | None, empty: bytes = b"null") -> Response:
    return Response(data or empty, media_type="application/json", headers={"Cache-Control": "no-store"})


def ok(data: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status, headers={"Cache-Control": "no-store"})


def err(status: int, msg: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"detail": msg, **extra}, status_code=status, headers={"Cache-Control": "no-store"})


async def body_of(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except (ValueError, UnicodeDecodeError):
        return {}


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"
