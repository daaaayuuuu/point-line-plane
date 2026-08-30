from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ApiError(Exception):
    code: str
    message: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.message


def not_found(resource: str = "资源") -> ApiError:
    return ApiError("NOT_FOUND", f"{resource}不存在或你无权访问。", 404)
