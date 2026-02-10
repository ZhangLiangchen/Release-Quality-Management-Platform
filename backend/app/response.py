from __future__ import annotations

from typing import Any

from fastapi import Request


def success_response(request: Request, data: Any) -> dict[str, Any]:
    trace_id = getattr(request.state, "trace_id", "")
    return {"data": data, "trace_id": trace_id}
