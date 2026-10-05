"""安全培训业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.services.certificate import CertificateService
from app.store import ARCHIVED_DATE_FIELD, store

MODULE = "training"
REQUIRED_FIELDS = ["培训编号", "培训主题", "培训对象"]
STATUS_ORDER = ["待培训", "培训中", "已考核", "已归档"]
ACTION_RULES = {"组织培训": "培训中", "组织考核": "已考核", "归档": "已归档"}
NEGATIVE_ACTIONS = []
ARCHIVED_STATUS = STATUS_ORDER[-1]

certificate_service = CertificateService()


class TrainingService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        exam_result: str | None = None,
        target: str | None = None,
        train_date: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """先在完整索引里定范围再分页：已归档记录同样在检索范围内。

        考核结果精确比对（避免「合格」把「不合格」带出来），培训对象按姓名模糊
        匹配，培训日期按前缀匹配（输到月份就框住整月），三个条件可以组合。
        """
        rows = list(store.index(MODULE))
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("培训编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if exam_result:
            rows = [row for row in rows if str(row.get("考核结果", "")) == exam_result]
        if target:
            rows = [row for row in rows if target in str(row.get("培训对象", ""))]
        if train_date:
            rows = [row for row in rows if str(row.get("培训日期", "")).startswith(train_date)]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        """详情与列表读同一份索引记录，已归档记录照常可读。"""
        return store.find_in_index(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["培训状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        store.index_add(MODULE, entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"培训记录 {entry_id} 不存在"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于安全培训可执行范围"
        if entry.get("status") == ARCHIVED_STATUS:
            archived_at = entry.get(ARCHIVED_DATE_FIELD) or "归档日期未落库"
            return None, f"培训记录已于 {archived_at} 归档，归档状态以首次落库为准，不能再执行「{action}」"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["培训状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if target != ARCHIVED_STATUS:
            return entry, f"培训记录已{action}"
        # 归档日期只在第一次落库时写入，之后不再改写。
        entry.setdefault(ARCHIVED_DATE_FIELD, date.today().isoformat())
        store.index_refresh(MODULE, entry)
        reminded = certificate_service.refresh_retraining(entry)
        if reminded:
            return entry, f"培训记录已{action}，{len(reminded)} 名持证人员的复训提醒已更新"
        return entry, f"培训记录已{action}"
