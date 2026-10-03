from app.services.fill_engine import build_fill_lines, compute_gap, normalize_case_qty, round_fill_to_case, summarize

def _lane(lid=1, slot="A1", sku="水", cap=20, stock=5, transit=0, case=1):
    return {"id": lid, "slot_no": slot, "sku_name": sku,
            "capacity": cap, "stock": stock, "in_transit": transit, "case_qty": case}

def test_gap_basic():
    assert compute_gap(20, 5, 0) == 15
    assert compute_gap(20, 10, 5) == 5

def test_no_negative_fill():
    lines = build_fill_lines([_lane(cap=10, stock=12)])
    assert lines[0].fill_qty == 0
    assert lines[0].status == "overbooked"

def test_cap_by_gap():
    lines = build_fill_lines([_lane(cap=20, stock=5)], requested={1: 100})
    assert lines[0].fill_qty == 15
    assert lines[0].gap == 15

def test_full_zero_fill():
    s = summarize(build_fill_lines([_lane(cap=10, stock=8, transit=2)]))
    assert s["full_count"] == 1
    assert s["total_fill"] == 0

def test_case_qty_normalization():
    assert normalize_case_qty(None) == 1
    assert normalize_case_qty(0) == 1
    assert normalize_case_qty(-3) == 1
    assert normalize_case_qty(4) == 4

def test_seed_b1_scenario():
    """种子 B1：箱规 4、缺口 7 → 补量只能是 4。"""
    lines = build_fill_lines([_lane(slot="B1", sku="薯片", cap=12, stock=3, transit=2, case=4)])
    l = lines[0]
    assert l.gap == 7
    assert l.fill_qty == 4
    assert l.status == "need_fill"

def test_round_down_to_case_multiple():
    assert round_fill_to_case(7, 4) == 4
    assert round_fill_to_case(8, 4) == 8
    assert round_fill_to_case(9, 4) == 8
    assert round_fill_to_case(1, 4) == 0

def test_gap_but_less_than_one_case_is_still_need_fill():
    """缺口 7、箱规 8：取整后补量 0，但物理缺口 > 0，状态必须仍是待补，禁止改写成满仓。"""
    lines = build_fill_lines([_lane(cap=10, stock=3, case=8)])
    l = lines[0]
    assert l.gap == 7
    assert l.fill_qty == 0
    assert l.status == "need_fill"
    s = summarize(lines)
    assert s["need_fill_count"] == 1
    assert s["full_count"] == 0
    assert s["total_fill"] == 0

def test_less_than_case_and_full_are_mutually_exclusive():
    lanes = [
        _lane(lid=1, cap=10, stock=3, case=8),   # 缺 7，不足一箱 → 待补
        _lane(lid=2, cap=10, stock=10, case=8),  # 缺 0 → 满仓
    ]
    s = summarize(build_fill_lines(lanes))
    assert s["need_fill_count"] == 1
    assert s["full_count"] == 1
    by_id = {l.lane_id: l for l in build_fill_lines(lanes)}
    assert by_id[1].status == "need_fill" and by_id[1].fill_qty == 0
    assert by_id[2].status == "full" and by_id[2].fill_qty == 0

def test_requested_capped_then_rounded():
    """先按缺口封顶，再向下取整；期望量不得越过缺口。"""
    lines = build_fill_lines([_lane(cap=10, stock=0, case=6)], requested={1: 7})
    assert lines[0].gap == 10
    assert lines[0].fill_qty == 6  # min(7,10)=7 → 向下取整 6
    lines = build_fill_lines([_lane(cap=10, stock=0, case=6)], requested={1: 100})
    assert lines[0].fill_qty == 6  # 封顶 10 → 6

def test_case_one_equals_piece_fill():
    """箱规留空或 1 与现网按件补完全相同。"""
    a = build_fill_lines([_lane(cap=20, stock=5)])
    b = build_fill_lines([{**_lane(cap=20, stock=5), "case_qty": None}])
    c = build_fill_lines([_lane(cap=20, stock=5, case=1)])
    assert [l.fill_qty for l in a] == [l.fill_qty for l in b] == [l.fill_qty for l in c] == [15]

def test_overbooked_unaffected_by_case():
    lines = build_fill_lines([_lane(cap=10, stock=12, case=6)])
    assert lines[0].status == "overbooked"
    assert lines[0].fill_qty == 0
