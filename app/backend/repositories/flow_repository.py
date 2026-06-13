from typing import List, Optional, Tuple
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session
from app.backend.database.models import HedgeFundFlow


class FlowRepository:
    """Repository for HedgeFundFlow CRUD operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_flow(self, name: str, nodes: dict, edges: dict, description: str = None, 
                   viewport: dict = None, data: dict = None, is_template: bool = False, tags: List[str] = None) -> HedgeFundFlow:
        """Create a new hedge fund flow"""
        flow = HedgeFundFlow(
            name=name,
            description=description,
            nodes=nodes,
            edges=edges,
            viewport=viewport,
            data=data,
            is_template=is_template,
            tags=tags or []
        )
        self.db.add(flow)
        self.db.commit()
        self.db.refresh(flow)
        return flow
    
    def get_flow_by_id(self, flow_id: int) -> Optional[HedgeFundFlow]:
        """Get a flow by its ID"""
        return self.db.query(HedgeFundFlow).filter(HedgeFundFlow.id == flow_id).first()
    
    def query_flows(
        self,
        *,
        is_template: Optional[bool] = None,
        keyword: Optional[str] = None,
        tags: Optional[List[str]] = None,
        sort_order: str = "desc",
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[HedgeFundFlow], int]:
        """Query flows with optional template/keyword/tag filters, sorted by last
        update time, returning the requested page and the total match count.

        - keyword: case-insensitive partial match against name, description, or tags.
        - tags: exact match against any of the given tags (JSON array membership).
        - sort_order: "asc" or "desc" on COALESCE(updated_at, created_at).
        """
        query = self.db.query(HedgeFundFlow)

        if is_template is not None:
            query = query.filter(HedgeFundFlow.is_template == is_template)

        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                or_(
                    HedgeFundFlow.name.ilike(like),
                    HedgeFundFlow.description.ilike(like),
                    cast(HedgeFundFlow.tags, String).ilike(like),
                )
            )

        if tags:
            # Match flows whose JSON `tags` array contains any of the requested tags.
            each_tag = func.json_each(HedgeFundFlow.tags).table_valued("value")
            tag_exists = (
                select(1).select_from(each_tag).where(each_tag.c.value.in_(tags)).exists()
            )
            query = query.filter(HedgeFundFlow.tags.isnot(None), tag_exists)

        total = query.count()

        # updated_at is NULL until a flow is edited, so fall back to created_at.
        order_col = func.coalesce(HedgeFundFlow.updated_at, HedgeFundFlow.created_at)
        direction = order_col.asc() if sort_order == "asc" else order_col.desc()

        items = (
            query.order_by(direction, HedgeFundFlow.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total
    
    def update_flow(self, flow_id: int, name: str = None, description: str = None,
                   nodes: dict = None, edges: dict = None, viewport: dict = None, data: dict = None,
                   is_template: bool = None, tags: List[str] = None) -> Optional[HedgeFundFlow]:
        """Update an existing flow"""
        flow = self.get_flow_by_id(flow_id)
        if not flow:
            return None
        
        if name is not None:
            flow.name = name
        if description is not None:
            flow.description = description
        if nodes is not None:
            flow.nodes = nodes
        if edges is not None:
            flow.edges = edges
        if viewport is not None:
            flow.viewport = viewport
        if data is not None:
            flow.data = data
        if is_template is not None:
            flow.is_template = is_template
        if tags is not None:
            flow.tags = tags
        
        self.db.commit()
        self.db.refresh(flow)
        return flow
    
    def delete_flow(self, flow_id: int) -> bool:
        """Delete a flow by ID"""
        flow = self.get_flow_by_id(flow_id)
        if not flow:
            return False
        
        self.db.delete(flow)
        self.db.commit()
        return True
    
    def duplicate_flow(self, flow_id: int, new_name: str = None) -> Optional[HedgeFundFlow]:
        """Create a copy of an existing flow"""
        original = self.get_flow_by_id(flow_id)
        if not original:
            return None
        
        copy_name = new_name or f"{original.name} (Copy)"
        
        return self.create_flow(
            name=copy_name,
            description=original.description,
            nodes=original.nodes,
            edges=original.edges,
            viewport=original.viewport,
            data=original.data,
            is_template=False,  # Copies are not templates by default
            tags=original.tags
        ) 