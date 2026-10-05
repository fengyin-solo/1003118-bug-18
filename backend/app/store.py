"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
检索索引与台账同一份记录对象：列表、详情、导出读到的永远是同一条记录。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS

# 各模块的收档终态：进入该状态的记录必须留在检索索引里，不能被过滤掉。
ARCHIVED_STATUS = {"training": "已归档"}
# 归档时间字段：只在第一次归档落库时写入，索引回填按它排序，之后不再改写。
ARCHIVED_DATE_FIELD = "归档日期"


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        self._indexes: dict[str, list[dict[str, Any]]] = {
            name: self._build_index(name) for name in self._tables
        }

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def _is_archived(self, module: str, row: dict[str, Any]) -> bool:
        archived_status = ARCHIVED_STATUS.get(module)
        return archived_status is not None and row.get("status") == archived_status

    def _build_index(self, module: str) -> list[dict[str, Any]]:
        """重建检索索引：在办记录保持登记顺序，旧归档记录按归档日期回填。"""
        rows = self._tables.get(module, [])
        active = [row for row in rows if not self._is_archived(module, row)]
        archived = [row for row in rows if self._is_archived(module, row)]
        archived.sort(key=lambda row: str(row.get(ARCHIVED_DATE_FIELD) or ""))
        return [*active, *archived]

    def index(self, module: str) -> list[dict[str, Any]]:
        """检索索引：覆盖在办与已归档的全部记录，筛选口径都以它为准。"""
        return self._indexes.setdefault(module, self._build_index(module))

    def find_in_index(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.index(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def index_add(self, module: str, row: dict[str, Any]) -> None:
        """新登记记录进入索引：在办段保持登记顺序，归档段不受影响。"""
        entries = self.index(module)
        position = next(
            (i for i, item in enumerate(entries) if self._is_archived(module, item)),
            len(entries),
        )
        entries.insert(position, row)

    def index_refresh(self, module: str, row: dict[str, Any]) -> None:
        """记录状态流转后重新归位：归档记录按归档日期插回归档段。"""
        entries = self.index(module)
        entries[:] = [item for item in entries if item is not row]
        if self._is_archived(module, row):
            archived_date = str(row.get(ARCHIVED_DATE_FIELD) or "")
            position = next(
                (
                    i
                    for i, item in enumerate(entries)
                    if self._is_archived(module, item)
                    and str(item.get(ARCHIVED_DATE_FIELD) or "") > archived_date
                ),
                len(entries),
            )
            entries.insert(position, row)
        else:
            self.index_add(module, row)

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
