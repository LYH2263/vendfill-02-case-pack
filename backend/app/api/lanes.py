from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Lane, RefillOrder
from app.services.fill_engine import compute_gap
from app.services.orders import build_order_summary
import json

router = APIRouter(prefix="/lanes", tags=["lanes"])


class LaneUpdate(BaseModel):
    # 箱规件数（正整数）；留空/None 视为 1（按件补）；<=0 打回，三处不动
    case_qty: int | None = None


def _lane_out(r: Lane) -> dict:
    gap = compute_gap(r.capacity, r.stock, r.in_transit)
    return {"id": r.id, "location_id": r.location_id, "slot_no": r.slot_no, "sku_name": r.sku_name,
            "capacity": r.capacity, "stock": r.stock, "in_transit": r.in_transit,
            "case_qty": r.case_qty if r.case_qty is not None else 1, "gap": gap,
            "fill_pct": round(r.stock / r.capacity * 100, 1) if r.capacity else 0}


@router.get("")
def list_lanes(location_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Lane).order_by(Lane.slot_no)
    if location_id is not None: q = q.where(Lane.location_id == location_id)
    return [_lane_out(r) for r in db.scalars(q).all()]


@router.put("/{lane_id}")
def update_lane(lane_id: int, payload: LaneUpdate, db: Session = Depends(get_db)):
    """改箱规并保存。

    若该点位已有最新补货单，必须在同一次提交里按新箱规重写该单全部行：
    重写成功则货道箱规、最新单、汇总一起变；任一步失败整体回滚，
    不许出现字段已新、小票仍旧的半截成功。历史其它补货单不动。
    """
    lane = db.get(Lane, lane_id)
    if not lane:
        raise HTTPException(404, "货道不存在")
    case_qty = 1 if payload.case_qty is None else payload.case_qty
    if case_qty <= 0:
        # 非法值：不发起任何写库动作，箱规字段与所有单据都保持原样
        raise HTTPException(400, "箱规必须为正整数（留空视为 1）")

    rewritten_order_id: int | None = None
    try:
        lane.case_qty = case_qty
        db.flush()  # 先让约束/类型错误在这里暴露

        latest_order = db.scalars(
            select(RefillOrder).where(RefillOrder.location_id == lane.location_id)
            .order_by(RefillOrder.id.desc())
        ).first()
        if latest_order is not None:
            lanes = db.scalars(
                select(Lane).where(Lane.location_id == lane.location_id).order_by(Lane.slot_no)
            ).all()
            # 同一引擎口径重写该单全部行；箱规已改，汇总随之一起变
            latest_order.lines_json = json.dumps(build_order_summary(lanes), ensure_ascii=False)
            rewritten_order_id = latest_order.id
            db.flush()

        db.commit()
    except Exception:
        db.rollback()  # 箱规字段与单据内容一并退回保存前
        raise
    db.refresh(lane)
    return {**_lane_out(lane), "rewritten_order_id": rewritten_order_id}
