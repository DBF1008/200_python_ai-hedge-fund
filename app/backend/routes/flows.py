from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.backend.database import get_db
from app.backend.repositories.flow_repository import FlowRepository
from app.backend.models.schemas import (
    FlowCreateRequest,
    FlowUpdateRequest,
    FlowResponse,
    FlowSummaryResponse,
    FlowListResponse,
    ErrorResponse
)

router = APIRouter(prefix="/flows", tags=["flows"])


@router.post(
    "/",
    response_model=FlowResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def create_flow(request: FlowCreateRequest, db: Session = Depends(get_db)):
    """Create a new hedge fund flow"""
    try:
        repo = FlowRepository(db)
        flow = repo.create_flow(
            name=request.name,
            description=request.description,
            nodes=request.nodes,
            edges=request.edges,
            viewport=request.viewport,
            data=request.data,
            is_template=request.is_template,
            tags=request.tags
        )
        return FlowResponse.from_orm(flow)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create flow: {str(e)}")


@router.get(
    "/",
    response_model=FlowListResponse,
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_flows(
    is_template: Optional[bool] = Query(
        None, description="Filter by template (true) / non-template (false); omit for all"
    ),
    keyword: Optional[str] = Query(
        None, description="Case-insensitive match against name, description, or tags"
    ),
    tags: Optional[List[str]] = Query(
        None, description="Filter to flows containing any of these exact tags"
    ),
    sort_order: str = Query(
        "desc", pattern="^(asc|desc)$", description="Sort by last update time"
    ),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List flows (summary view) with filtering, search, and pagination"""
    try:
        repo = FlowRepository(db)
        flows, total = repo.query_flows(
            is_template=is_template,
            keyword=keyword,
            tags=tags,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        )
        return FlowListResponse(
            items=[FlowSummaryResponse.from_orm(flow) for flow in flows],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve flows: {str(e)}")


@router.get(
    "/{flow_id}",
    response_model=FlowResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Flow not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_flow(flow_id: int, db: Session = Depends(get_db)):
    """Get a specific flow by ID"""
    try:
        repo = FlowRepository(db)
        flow = repo.get_flow_by_id(flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")
        return FlowResponse.from_orm(flow)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve flow: {str(e)}")


@router.put(
    "/{flow_id}",
    response_model=FlowResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Flow not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def update_flow(flow_id: int, request: FlowUpdateRequest, db: Session = Depends(get_db)):
    """Update an existing flow"""
    try:
        repo = FlowRepository(db)
        flow = repo.update_flow(
            flow_id=flow_id,
            name=request.name,
            description=request.description,
            nodes=request.nodes,
            edges=request.edges,
            viewport=request.viewport,
            data=request.data,
            is_template=request.is_template,
            tags=request.tags
        )
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")
        return FlowResponse.from_orm(flow)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update flow: {str(e)}")


@router.delete(
    "/{flow_id}",
    responses={
        204: {"description": "Flow deleted successfully"},
        404: {"model": ErrorResponse, "description": "Flow not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def delete_flow(flow_id: int, db: Session = Depends(get_db)):
    """Delete a flow"""
    try:
        repo = FlowRepository(db)
        success = repo.delete_flow(flow_id)
        if not success:
            raise HTTPException(status_code=404, detail="Flow not found")
        return {"message": "Flow deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete flow: {str(e)}")


@router.post(
    "/{flow_id}/duplicate",
    response_model=FlowResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Flow not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def duplicate_flow(flow_id: int, new_name: str = None, db: Session = Depends(get_db)):
    """Create a copy of an existing flow"""
    try:
        repo = FlowRepository(db)
        flow = repo.duplicate_flow(flow_id, new_name)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")
        return FlowResponse.from_orm(flow)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to duplicate flow: {str(e)}")