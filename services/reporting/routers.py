"""Authenticated read and manual-trigger endpoints for weekly reports."""

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlmodel import Session

from database import get_db
from models import UserResponse
from security import get_current_user
from services.reporting.models import PipelineRun, WeeklyWarehouseClientPerformance

router = APIRouter(
    prefix="/reporting",
    tags=["Reporting"],
    dependencies=[Depends(get_current_user)],
)


class ManualRunRequest(BaseModel):
    week_start: Optional[date] = None


class ManualRunResponse(BaseModel):
    run_id: str
    state: str
    started_at: datetime


@router.get("/weekly-warehouse-client-performance")
def weekly_performance(
    week_start: Optional[date] = None,
    session: Session = Depends(get_db),
    _current_user: UserResponse = Depends(get_current_user),
):
    selected_week = week_start
    if selected_week is None:
        selected_week = session.scalar(
            select(func.max(WeeklyWarehouseClientPerformance.week_start))
        )
        if selected_week is None:
            return []
    rows = session.scalars(
        select(WeeklyWarehouseClientPerformance)
        .where(WeeklyWarehouseClientPerformance.week_start == selected_week)
        .order_by(
            WeeklyWarehouseClientPerformance.warehouse,
            WeeklyWarehouseClientPerformance.client_id,
        )
    ).all()
    return jsonable_encoder(rows)


@router.get("/pipeline-runs/latest")
def latest_pipeline_run(
    session: Session = Depends(get_db),
    _current_user: UserResponse = Depends(get_current_user),
):
    run = session.scalars(
        select(PipelineRun)
        .order_by(PipelineRun.started_at.desc(), PipelineRun.id.desc())
        .limit(1)
    ).first()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No pipeline runs found")
    return jsonable_encoder(run)


@router.post("/pipeline-runs", response_model=ManualRunResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_pipeline_run(
    payload: ManualRunRequest,
    session: Session = Depends(get_db),
    _current_user: UserResponse = Depends(get_current_user),
):
    """Run the canonical Prefect flow inline; transformations are not duplicated."""
    from data.pipelines.pipeline import (
        most_recent_completed_week,
        weekly_warehouse_client_performance_flow,
    )

    selected_week = payload.week_start or most_recent_completed_week()
    # Validate before scheduling/invoking the flow; no detached task or duplicate logic.
    if selected_week.weekday() != 0:
        raise HTTPException(
            status_code=422, detail="week_start_must_be_monday")
    state = weekly_warehouse_client_performance_flow(
        selected_week, return_state=True
    )
    if state.is_failed():
        error = state.result(raise_on_failure=False)
        safe_detail = "source_contract_violation" if error.__class__.__name__ == "ContractViolation" else "pipeline_run_failed"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=safe_detail)
    result = state.result()
    run_id = result["run_id"]
    run = session.get(PipelineRun, run_id)
    started_at = run.started_at if run else datetime.now(timezone.utc)
    return ManualRunResponse(
        run_id=run_id,
        state=result["state"],
        started_at=started_at,
    )
