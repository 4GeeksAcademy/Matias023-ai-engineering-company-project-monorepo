from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from tinydb import Query as TinyQuery

from cache import (
    INCIDENT_CACHE_NAMESPACE,
    INCIDENT_SUMMARY_TTL_SECONDS as _SUMMARY_TTL,
    cache,
)
from database import document_to_dict, incidents_table
from models import (
    IncidentBranch,
    IncidentCategory,
    IncidentCreate,
    IncidentOrigin,
    IncidentResponse,
    IncidentStatus,
    IncidentStatusUpdate,
    IncidentSummaryResponse,
)
from security import get_current_user


router = APIRouter(
    tags=["Incidents"],
    dependencies=[Depends(get_current_user)],
)


VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "open": {"in_progress", "discarded"},
    "in_progress": {"resolved", "discarded"},
    "resolved": set(),
    "discarded": set(),
}
ALL_STATUSES: list[IncidentStatus] = ["open", "in_progress", "resolved", "discarded"]

ALL_CATEGORIES: list[IncidentCategory] = [
    "lost_parcel",
    "delivery_failure",
    "inventory_discrepancy",
    "carrier_issue",
    "returns_issue",
    "warehouse_incident",
    "system_failure",
    "client_complaint",
    "other",
]

ALL_ORIGINS: list[IncidentOrigin] = ["customer", "branch", "internal"]

ALL_BRANCHES: list[IncidentBranch] = [
    "central",
    "la_warehouse",
    "la_office",
    "zaragoza_warehouse",
    "zaragoza_office",
]


def get_incident_or_404(incident_id: int):
    incident = incidents_table.get(doc_id=incident_id)

    if incident is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )

    return incident


@router.post(
    "",
    response_model=IncidentResponse,
    status_code=http_status.HTTP_201_CREATED,
)
def create_incident(payload: IncidentCreate):
    now = datetime.now(timezone.utc).isoformat()

    record = payload.model_dump()
    record["created_at"] = now
    record["updated_at"] = now

    incident_id = incidents_table.insert(record)
    incident = incidents_table.get(doc_id=incident_id)

    # A new incident affects status/category/origin/branch counts → invalidate
    cache.invalidate_prefix(INCIDENT_CACHE_NAMESPACE)

    return document_to_dict(incident)


@router.get("/summary", response_model=IncidentSummaryResponse)
def get_incidents_summary():
    # Authorisation dependency already executed via router-level Depends.
    # The cached response is shared across all authorised users because it
    # aggregates public incident metadata (counts by status/category/origin/
    # branch) — no per-user private fields are exposed.
    cached = cache.get("incidents:summary")
    if cached is not None:
        return cached

    documents = incidents_table.all()

    by_status = {value: 0 for value in ALL_STATUSES}
    by_category = {value: 0 for value in ALL_CATEGORIES}
    by_origin = {value: 0 for value in ALL_ORIGINS}
    by_branch = {value: 0 for value in ALL_BRANCHES}

    for document in documents:
        by_status[document["status"]] += 1
        by_category[document["category"]] += 1
        by_origin[document["origin"]] += 1
        by_branch[document["branch"]] += 1

    result = {
        "total": len(documents),
        "by_status": by_status,
        "by_category": by_category,
        "by_origin": by_origin,
        "by_branch": by_branch,
    }

    cache.set("incidents:summary", result, ttl=_SUMMARY_TTL)
    return result


@router.get("", response_model=list[IncidentResponse])
def list_incidents(
    status: IncidentStatus | None = None,
    origin: IncidentOrigin | None = None,
    branch: IncidentBranch | None = None,
    category: IncidentCategory | None = None,
):
    Incident = TinyQuery()
    conditions = []

    if status is not None:
        conditions.append(Incident.status == status)
    if origin is not None:
        conditions.append(Incident.origin == origin)
    if branch is not None:
        conditions.append(Incident.branch == branch)
    if category is not None:
        conditions.append(Incident.category == category)

    if conditions:
        query = conditions[0]
        for condition in conditions[1:]:
            query = query & condition
        documents = incidents_table.search(query)
    else:
        documents = incidents_table.all()

    return [document_to_dict(document) for document in documents]


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(incident_id: int):
    incident = get_incident_or_404(incident_id)

    return document_to_dict(incident)


@router.patch("/{incident_id}/status", response_model=IncidentResponse)
def update_incident_status(incident_id: int, payload: IncidentStatusUpdate):
    incident = get_incident_or_404(incident_id)
    current_status = incident["status"]

    if payload.status not in VALID_STATUS_TRANSITIONS[current_status]:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition status from '{current_status}' to '{payload.status}'",
        )

    incidents_table.update(
        {
            "status": payload.status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        doc_ids=[incident_id],
    )

    incident = get_incident_or_404(incident_id)

    # Status change affects by_status counts in summary → invalidate
    cache.invalidate_prefix(INCIDENT_CACHE_NAMESPACE)

    return document_to_dict(incident)
