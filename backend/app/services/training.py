"""安全培训业务规则：状态流转、字段校验与筛选口径都收在这里。

检索口径：先在完整索引（含已归档记录）上按组合条件定范围，再分页；
归档状态、归档日期随记录一起落库，只认第一次落库的结果。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "training"
REQUIRED_FIELDS = ["培训编号", "培训主题", "培训对象"]
ENTRY_FIELDS = ["培训编号", "培训主题", "培训对象", "培训日期", "培训讲师", "考核方式", "考核结果", "培训状态"]
STATUS_ORDER = ["待培训", "培训中", "已考核", "已归档"]
ACTION_RULES = {"组织培训": "培训中", "组织考核": "已考核", "归档": "已归档"}
NEGATIVE_ACTIONS = []
ARCHIVED_STATUS = STATUS_ORDER[-1]
# 归档落库字段受保护：只允许第一次归档时写入，后续动作不得改写
PROTECTED_FIELDS = {"id", "status", "pending", "abnormal", "归档状态", "归档日期"}

# 检索索引覆盖的字段：归档状态、归档日期必须随记录一起落库，否则已归档记录搜不到
INDEX_FIELDS = ["培训编号", "培训主题", "培训对象", "培训日期", "考核结果", "status", "归档状态", "归档日期"]


def backfill_archive(row: dict[str, Any]) -> None:
    """旧归档记录回填：按归档日期补进索引；已落库的归档结果不改写。"""
    if row.get("status") != ARCHIVED_STATUS or row.get("归档状态"):
        return
    row["归档状态"] = ARCHIVED_STATUS
    row["归档日期"] = str(row.get("归档日期") or row.get("培训日期") or date.today().isoformat())


def stamp_archive(row: dict[str, Any]) -> None:
    """归档动作落库：归档状态只认第一次落库的结果，重复归档不改写。"""
    if row.get("归档状态"):
        return
    row["归档状态"] = ARCHIVED_STATUS
    row["归档日期"] = date.today().isoformat()


class TrainingIndex:
    """培训检索索引：在办与已归档记录同库同口径，列表、详情、复训提醒读同一份。"""

    def __init__(self) -> None:
        self._docs: dict[int, dict[str, Any]] = {}

    def rebuild(self, rows: list[dict[str, Any]]) -> None:
        self._docs = {}
        for row in rows:
            backfill_archive(row)
            self.upsert(row)

    def upsert(self, row: dict[str, Any]) -> None:
        entry_id = int(row.get("id", 0))
        doc = {"id": entry_id}
        doc.update({field: row.get(field) for field in INDEX_FIELDS})
        self._docs[entry_id] = doc

    def docs(self) -> list[dict[str, Any]]:
        return [self._docs[key] for key in sorted(self._docs)]

    def archived(self) -> list[dict[str, Any]]:
        return [doc for doc in self.docs() if doc.get("归档状态") == ARCHIVED_STATUS]


training_index = TrainingIndex()


def _sync_retraining() -> None:
    """索引里补进的考核结果要同步到持证台账的复训提醒。"""
    from app.services.certificate import CertificateService

    CertificateService().sync_retraining(training_index.archived())


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
        # 先定范围：关键词、状态、考核结果、培训对象、培训日期组合过滤，已归档记录一并参与
        docs = training_index.docs()
        if keyword:
            docs = [doc for doc in docs if keyword in str(doc.get("培训编号") or "")]
        if status:
            docs = [doc for doc in docs if doc.get("status") == status]
        if exam_result:
            # 考核结果按精确值比对：「合格」不该把「不合格」一起捞出来
            docs = [doc for doc in docs if str(doc.get("考核结果") or "") == exam_result]
        if target:
            docs = [doc for doc in docs if target in str(doc.get("培训对象") or "")]
        if train_date:
            docs = [doc for doc in docs if str(doc.get("培训日期") or "") == train_date]
        # 再分页：总数按限定后的范围算，和实际条数对得上
        total = len(docs)
        start = max(page - 1, 0) * size
        selected = docs[start:start + size]
        # 列表与详情读同一条记录：按 id 回台账取完整行
        rows_by_id = {int(row.get("id", 0)): row for row in store.rows(MODULE)}
        items = [rows_by_id[doc["id"]] for doc in selected if doc["id"] in rows_by_id]
        return items, total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in ENTRY_FIELDS if values.get(field) is not None})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        training_index.upsert(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"培训记录 {entry_id} 不存在"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于安全培训可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        # 随动作提交的考核结果等字段一起落库；归档落库字段受保护，不允许随动作改写
        for field, value in (values or {}).items():
            if field in ENTRY_FIELDS and field not in PROTECTED_FIELDS and value is not None:
                entry[field] = value
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if target == ARCHIVED_STATUS:
            stamp_archive(entry)
        training_index.upsert(entry)
        _sync_retraining()
        return entry, f"培训记录已{action}"


# 启动时把台账全量（含旧归档记录）重建进索引，并让持证人员的复训提醒跟上
training_index.rebuild(store.rows(MODULE))
_sync_retraining()
