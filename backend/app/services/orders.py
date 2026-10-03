"""补货单落库/重写共用：统一从 ORM 货道行构造引擎输入。"""
from __future__ import annotations
from app.services.fill_engine import build_fill_lines, summarize


def lanes_to_payload(lanes) -> list[dict]:
    return [
        {
            "id": l.id,
            "slot_no": l.slot_no,
            "sku_name": l.sku_name,
            "capacity": l.capacity,
            "stock": l.stock,
            "in_transit": l.in_transit,
            "case_qty": l.case_qty if l.case_qty is not None else 1,
        }
        for l in lanes
    ]


def build_order_summary(lanes, requested: dict[int, int] | None = None) -> dict:
    return summarize(build_fill_lines(lanes_to_payload(lanes), requested))
