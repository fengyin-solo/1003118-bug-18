"""持证管理业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import ARCHIVED_DATE_FIELD, store

MODULE = "certificate"
REQUIRED_FIELDS = ["人员编号", "姓名", "证书类别"]
STATUS_ORDER = ["持证有效", "即将到期", "已过期", "已注销"]
ACTION_RULES = {"安排复训": "持证有效", "登记过期": "已过期", "注销证书": "已注销"}
NEGATIVE_ACTIONS = []


class CertificateService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("人员编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"持证人员 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于持证管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"持证人员已{action}"

    def refresh_retraining(self, training: dict[str, Any]) -> list[str]:
        """培训记录归档进入检索索引后，同步持证人员的复训提醒。

        按培训对象里的姓名匹配持证人员：考核合格记为复训完成，否则提醒再次
        复训；复训记录指向最新归档的培训编号与归档日期，其他台账读到的就是
        这同一份数据。
        """
        attendees = str(training.get("培训对象") or "")
        if not attendees.strip():
            return []
        passed = str(training.get("考核结果") or "") == "合格"
        record = f"{training.get('培训编号', '')}（{training.get(ARCHIVED_DATE_FIELD, '')}归档）"
        reminded: list[str] = []
        for row in store.rows(MODULE):
            name = str(row.get("姓名") or "").strip()
            if name and name in attendees:
                row["复训记录"] = record
                row["复训提醒"] = "复训已完成" if passed else "复训未通过，需再次复训"
                reminded.append(name)
        return reminded
