"""Vending refill.

统一箱规口径（货道编辑 / 最新补货单 / 汇总必须走这一套）：
gap = capacity - stock - in_transit
可补量先按缺口封顶，再向下取整到箱规整数倍；取整后为 0 则补量为 0，
但只要物理缺口仍大于 0，状态仍是 need_fill —— 「不足一整箱」与「已满仓」互斥。
箱规留空或 1 时即按件补（与现网相同）。
"""
from __future__ import annotations
from dataclasses import asdict, dataclass

@dataclass
class FillLine:
    lane_id: int
    slot_no: str
    sku_name: str
    capacity: int
    stock: int
    in_transit: int
    case_qty: int
    gap: int
    fill_qty: int
    status: str  # need_fill | full | overbooked

def compute_gap(capacity: int, stock: int, in_transit: int) -> int:
    return capacity - stock - in_transit

def normalize_case_qty(case_qty: int | None) -> int:
    """空值/非正数/1 一律归一为 1（按件补）。>1 必须为正整数。"""
    if case_qty is None:
        return 1
    try:
        c = int(case_qty)
    except (TypeError, ValueError):
        return 1
    return c if c > 1 else 1

def round_fill_to_case(desired: int, case_qty: int) -> int:
    """先保证非负，再向下取整到箱规整数倍。"""
    case = normalize_case_qty(case_qty)
    if desired <= 0:
        return 0
    return (desired // case) * case

def build_fill_lines(lanes: list[dict], requested: dict[int, int] | None = None) -> list[FillLine]:
    """requested optional desired fill per lane_id.

    口径：缺口为负 → overbooked；缺口为 0 → full；缺口 > 0 → need_fill，
    期望量先按缺口封顶，再向下取整到箱规倍数；不足一箱时 fill_qty=0 但状态不改写。
    """
    lines: list[FillLine] = []
    for lane in lanes:
        gap = compute_gap(int(lane["capacity"]), int(lane["stock"]), int(lane["in_transit"]))
        case = normalize_case_qty(lane.get("case_qty"))
        if gap < 0:
            status = "overbooked"
            fill = 0
        elif gap == 0:
            status = "full"
            fill = 0
        else:
            # 物理缺口 > 0 永远是待补，哪怕不足一整箱、补量取整为 0
            status = "need_fill"
            desire = gap if requested is None else int(requested.get(lane["id"], gap))
            fill = round_fill_to_case(min(desire, gap), case)
        lines.append(FillLine(
            lane_id=lane["id"], slot_no=lane["slot_no"], sku_name=lane["sku_name"],
            capacity=lane["capacity"], stock=lane["stock"], in_transit=lane["in_transit"],
            case_qty=case, gap=gap, fill_qty=fill, status=status,
        ))
    return lines

def summarize(lines: list[FillLine]) -> dict:
    return {
        "total_fill": sum(l.fill_qty for l in lines),
        "need_fill_count": sum(1 for l in lines if l.status == "need_fill"),
        "full_count": sum(1 for l in lines if l.status == "full"),
        "overbooked_count": sum(1 for l in lines if l.status == "overbooked"),
        "lines": [asdict(l) for l in lines],
    }
