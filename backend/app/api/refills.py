import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Lane, Location, RefillOrder
from app.services.orders import build_order_summary
router = APIRouter(prefix="/refills", tags=["refills"])

def _lanes_at(db: Session, location_id: int):
    return db.scalars(
        select(Lane).where(Lane.location_id == location_id).order_by(Lane.slot_no)
    ).all()

def _store_order(db: Session, location_id: int, lanes) -> tuple[RefillOrder, dict]:
    summary = build_order_summary(lanes)
    order = RefillOrder(location_id=location_id, created_at=datetime.utcnow(),
                        lines_json=json.dumps(summary, ensure_ascii=False))
    db.add(order); db.commit(); db.refresh(order)
    return order, summary

@router.post("/run")
def run_refill(location_id: int = 1, db: Session = Depends(get_db)):
    loc = db.get(Location, location_id)
    if not loc: raise HTTPException(404, "点位不存在")
    order, summary = _store_order(db, location_id, _lanes_at(db, location_id))
    return {"id": order.id, "location_id": location_id, **summary}

@router.get("/latest")
def latest(location_id: int = 1, db: Session = Depends(get_db)):
    loc = db.get(Location, location_id)
    if not loc: raise HTTPException(404, "点位不存在")
    order = db.scalars(select(RefillOrder).where(RefillOrder.location_id == location_id)
                       .order_by(RefillOrder.id.desc())).first()
    if not order:
        order, summary = _store_order(db, location_id, _lanes_at(db, location_id))
        return {"id": order.id, "location_id": location_id, **summary}
    data = json.loads(order.lines_json)
    return {"id": order.id, "location_id": location_id, **data}

@router.get("/full")
def full_lanes(location_id: int = 1, db: Session = Depends(get_db)):
    data = latest(location_id=location_id, db=db)
    # 满仓：物理缺口为 0；不足一整箱（fill=0 但 need_fill）不算满仓
    return {"location_id": location_id, "lanes": [l for l in data["lines"] if l["status"] == "full"]}

@router.get("/summary")
def refill_summary(location_id: int = 1, db: Session = Depends(get_db)):
    data = latest(location_id=location_id, db=db)
    return {
        "location_id": location_id,
        "total_fill": data["total_fill"],
        "need_fill_count": data["need_fill_count"],
        "short_case_count": sum(
            1 for l in data["lines"] if l["status"] == "need_fill" and l["fill_qty"] == 0
        ),
        "full_count": data["full_count"],
        "overbooked_count": data["overbooked_count"],
    }
