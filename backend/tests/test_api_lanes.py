"""箱规保存与最新补货单同事务重写的集成测试（SQLite，不走真实 PG/lifespan）。"""
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import Lane, Location, RefillOrder


SEED_LANES = [
    # slot, sku, cap, stock, transit, case_qty
    ("A1", "矿泉水", 20, 5, 0, 1),   # 缺 15
    ("B1", "薯片", 12, 3, 2, 1),     # 缺 7
]


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestingSession()
    loc = Location(id=1, code="VM-01", name="测试点位", address="")
    db.add(loc)
    db.flush()
    for slot, sku, cap, stock, transit, case in SEED_LANES:
        db.add(Lane(location_id=1, slot_no=slot, sku_name=sku, capacity=cap,
                    stock=stock, in_transit=transit, case_qty=case))
    db.commit()

    def override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestingSession
    app.dependency_overrides.clear()
    db.close()


@pytest.fixture()
def client(db_session):
    return TestClient(app)  # 不作为 context manager 使用 → 不触发 lifespan（不连真实 PG）


def _lane_id(db_session, slot: str) -> int:
    s = db_session()
    try:
        return s.scalar(select(Lane.id).where(Lane.slot_no == slot))
    finally:
        s.close()


def _line(data, slot: str) -> dict:
    return next(l for l in data["lines"] if l["slot_no"] == slot)


def test_lanes_list_exposes_case_qty(client):
    rows = client.get("/api/lanes").json()
    by_slot = {r["slot_no"]: r for r in rows}
    assert by_slot["B1"]["case_qty"] == 1


def test_put_case_qty_rewrites_latest_order_all_lines(client, db_session):
    r = client.post("/api/refills/run?location_id=1")
    assert r.status_code == 200
    order_id = r.json()["id"]
    assert _line(r.json(), "B1")["fill_qty"] == 7  # 箱规 1 → 按件补 7

    b1 = _lane_id(db_session, "B1")
    resp = client.put(f"/api/lanes/{b1}", json={"case_qty": 4})
    assert resp.status_code == 200
    assert resp.json()["case_qty"] == 4
    assert resp.json()["rewritten_order_id"] == order_id

    latest = client.get("/api/refills/latest?location_id=1").json()
    assert latest["id"] == order_id  # 重写而非新建
    b1_line = _line(latest, "B1")
    assert b1_line["gap"] == 7
    assert b1_line["fill_qty"] == 4  # 缺口 7、箱规 4 → 只能补 4
    assert b1_line["status"] == "need_fill"
    # 全部行按统一口径重写：A1 箱规仍是 1，补 15 不变
    assert _line(latest, "A1")["fill_qty"] == 15
    assert latest["total_fill"] == 19  # 汇总与单据同一套倍数口径

    s = db_session()
    try:
        # 没有新增单据
        assert s.scalar(select(RefillOrder).where(RefillOrder.id == order_id)) is not None
        assert len(s.scalars(select(RefillOrder)).all()) == 1
    finally:
        s.close()


def test_put_without_existing_order_creates_none_but_latest_uses_new_case(client, db_session):
    b1 = _lane_id(db_session, "B1")
    resp = client.put(f"/api/lanes/{b1}", json={"case_qty": 4})
    assert resp.status_code == 200
    assert resp.json()["rewritten_order_id"] is None
    s = db_session()
    try:
        assert len(s.scalars(select(RefillOrder)).all()) == 0  # 无单可改，不凭空建单
    finally:
        s.close()
    latest = client.get("/api/refills/latest?location_id=1").json()
    assert _line(latest, "B1")["fill_qty"] == 4  # 之后生成的单按新箱规


def test_invalid_case_qty_rolls_back_field_and_order(client, db_session):
    run = client.post("/api/refills/run?location_id=1").json()
    order_id = run["id"]
    s = db_session()
    try:
        original_json = s.get(RefillOrder, order_id).lines_json
    finally:
        s.close()

    b1 = _lane_id(db_session, "B1")
    for bad in (0, -3):
        resp = client.put(f"/api/lanes/{b1}", json={"case_qty": bad})
        assert resp.status_code == 400, bad

    # 箱规字段回滚
    s = db_session()
    try:
        lane = s.get(Lane, b1)
        assert lane.case_qty == 1
        # 单据内容逐字节退回保存前
        assert s.get(RefillOrder, order_id).lines_json == original_json
    finally:
        s.close()

    # 小票仍旧口径：B1 仍补 7
    latest = client.get("/api/refills/latest?location_id=1").json()
    assert _line(latest, "B1")["fill_qty"] == 7


def test_non_integer_case_qty_rejected_before_any_write(client, db_session):
    run = client.post("/api/refills/run?location_id=1").json()
    b1 = _lane_id(db_session, "B1")
    resp = client.put(f"/api/lanes/{b1}", json={"case_qty": "abc"})
    assert resp.status_code == 422
    s = db_session()
    try:
        assert s.get(Lane, b1).case_qty == 1
        assert len(s.scalars(select(RefillOrder)).all()) == 1
    finally:
        s.close()


def test_history_orders_not_rewritten(client, db_session):
    first = client.post("/api/refills/run?location_id=1").json()
    second = client.post("/api/refills/run?location_id=1").json()
    assert second["id"] != first["id"]

    b1 = _lane_id(db_session, "B1")
    client.put(f"/api/lanes/{b1}", json={"case_qty": 4})

    s = db_session()
    try:
        orders = s.scalars(select(RefillOrder).order_by(RefillOrder.id)).all()
        assert len(orders) == 2
        old = json.loads(orders[0].lines_json)
        new = json.loads(orders[1].lines_json)
        assert next(l for l in old["lines"] if l["slot_no"] == "B1")["fill_qty"] == 7
        assert next(l for l in new["lines"] if l["slot_no"] == "B1")["fill_qty"] == 4
    finally:
        s.close()


def test_less_than_one_case_still_need_fill_after_rewrite(client, db_session):
    client.post("/api/refills/run?location_id=1")
    b1 = _lane_id(db_session, "B1")  # 缺 7
    client.put(f"/api/lanes/{b1}", json={"case_qty": 8})  # 不足一整箱

    latest = client.get("/api/refills/latest?location_id=1").json()
    b1_line = _line(latest, "B1")
    assert b1_line["fill_qty"] == 0
    assert b1_line["status"] == "need_fill"  # 禁止改写成满仓
    assert latest["need_fill_count"] == 2
    assert latest["full_count"] == 0

    full = client.get("/api/refills/full?location_id=1").json()
    assert all(l["slot_no"] != "B1" for l in full["lanes"])


def test_summary_matches_latest_order_after_rewrite(client, db_session):
    client.post("/api/refills/run?location_id=1")
    b1 = _lane_id(db_session, "B1")
    client.put(f"/api/lanes/{b1}", json={"case_qty": 4})
    summary = client.get("/api/refills/summary?location_id=1").json()
    assert summary["total_fill"] == 19
    assert summary["need_fill_count"] == 2
    assert summary["short_case_count"] == 0


def test_summary_short_case_counted_as_need_fill(client, db_session):
    client.post("/api/refills/run?location_id=1")
    b1 = _lane_id(db_session, "B1")  # 缺 7
    client.put(f"/api/lanes/{b1}", json={"case_qty": 8})  # 不足一箱 → 补 0 仍待补
    summary = client.get("/api/refills/summary?location_id=1").json()
    assert summary["total_fill"] == 15  # 只有 A1 的 15
    assert summary["need_fill_count"] == 2
    assert summary["short_case_count"] == 1
    assert summary["full_count"] == 0
