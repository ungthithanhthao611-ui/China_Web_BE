from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def success_response(
    data: Any = None,
    message: str = "OK",
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": data,
            "message": message,
        },
    )


def error_response(
    message: str,
    *,
    errors: Any = None,
    status_code: int = 400,
) -> JSONResponse:
    payload: dict[str, Any] = {
        "success": False,
        "message": message,
    }
    if errors is not None:
        payload["errors"] = errors
    return JSONResponse(status_code=status_code, content=payload)

