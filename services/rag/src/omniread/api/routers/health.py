"""meta 路由：存活探针。

只报进程自身，不调 provider、不探 DB——健康检查不该有外部成本与抖动。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from omniread.api.deps import get_settings
from omniread.api.schemas import Health
from omniread.config import Settings

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=Health, operation_id="internalHealth")
def health(settings: Settings = Depends(get_settings)) -> Health:
    return Health(status="ok", service=settings.service_name)
