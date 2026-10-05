"""安全培训接口：维护培训记录，覆盖组织培训、组织考核、归档等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.training import TrainingService

router = APIRouter(prefix="/api/training", tags=["安全培训"])

service = TrainingService()

LIST_FIELDS = ["培训编号", "培训主题", "培训对象", "培训日期", "培训讲师", "考核方式", "考核结果", "培训状态", "归档状态", "归档日期"]
STATUSES = ["待培训", "培训中", "已考核", "已归档"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按培训编号检索"),
    status: str | None = Query(default=None, description="待培训、培训中、已考核、已归档"),
    exam_result: str | None = Query(default=None, description="按考核结果检索"),
    target: str | None = Query(default=None, description="按培训对象检索"),
    train_date: str | None = Query(default=None, description="按培训日期检索，格式如 2026-09-01"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """考核结果、培训对象、培训日期可组合过滤，先定范围再分页；已归档记录同样参与检索。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        status=status,
        exam_result=exam_result,
        target=target,
        train_date=train_date,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按培训编号检索"),
    status: str | None = Query(default=None, description="待培训、培训中、已考核、已归档"),
    exam_result: str | None = Query(default=None, description="按考核结果检索"),
    target: str | None = Query(default=None, description="按培训对象检索"),
    train_date: str | None = Query(default=None, description="按培训日期检索，格式如 2026-09-01"),
) -> dict[str, Any]:
    """导出安全培训清单：与列表同一检索口径，返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(
        keyword=keyword,
        status=status,
        exam_result=exam_result,
        target=target,
        train_date=train_date,
        page=1,
        size=10000,
    )
    return {"module": "training", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条培训记录明细；已归档记录同样可读，不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"培训记录 {entry_id} 不存在")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条培训记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="培训记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条培训记录执行组织培训、组织考核、归档；可随动作提交考核结果等字段一并落库。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
