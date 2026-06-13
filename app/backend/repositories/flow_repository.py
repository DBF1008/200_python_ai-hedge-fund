import json
from typing import List, Optional, Tuple
from sqlalchemy import Text, func, or_
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
    
    def get_all_flows(self, include_templates: bool = True) -> List[HedgeFundFlow]:
        """Get all flows, optionally excluding templates"""
        query = self.db.query(HedgeFundFlow)
        if not include_templates:
            query = query.filter(HedgeFundFlow.is_template == False)
        return query.order_by(HedgeFundFlow.updated_at.desc()).all()
    
    def get_flows_by_name(self, name: str) -> List[HedgeFundFlow]:
        """Search flows by name (case-insensitive partial match)"""
        return self.db.query(HedgeFundFlow).filter(
            HedgeFundFlow.name.ilike(f"%{name}%")
        ).order_by(HedgeFundFlow.updated_at.desc()).all()

    def search_flows(
        self,
        search: Optional[str] = None,
        is_template: Optional[bool] = None,
        tag: Optional[str] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[HedgeFundFlow], int]:
        """
        Unified search/filter/sort/paginate for flows.
        Returns (list_of_flows, total_count).
        """
        query = self.db.query(HedgeFundFlow)

        # Filter by template status
        if is_template is not None:
            query = query.filter(HedgeFundFlow.is_template == is_template)

        # Keyword search across name, description, and tags (JSON text)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    HedgeFundFlow.name.ilike(pattern),
                    HedgeFundFlow.description.ilike(pattern),
                    # SQLite stores JSON as text; cast to Text for ILIKE
                    HedgeFundFlow.tags.cast(Text).ilike(pattern),
                )
            )

        # Filter by a specific tag (JSON array contains)
        if tag:
            # SQLite JSON arrays are stored as '["tag1", "tag2"]'
            # Match the quoted tag string to avoid partial matches
            tag_pattern = f'%"{tag}"%'
            query = query.filter(
                HedgeFundFlow.tags.cast(Text).ilike(tag_pattern)
            )

        # Count before pagination
        total = query.count()

        # Sorting
        sort_column = {
            "name": HedgeFundFlow.name,
            "created_at": HedgeFundFlow.created_at,
            "updated_at": HedgeFundFlow.updated_at,
        }.get(sort_by, HedgeFundFlow.updated_at)

        # Handle NULL updated_at: coalesce to created_at
        if sort_by == "updated_at":
            sort_expr = func.coalesce(HedgeFundFlow.updated_at, HedgeFundFlow.created_at)
        else:
            sort_expr = sort_column

        if sort_order == "asc":
            query = query.order_by(sort_expr.asc())
        else:
            query = query.order_by(sort_expr.desc())

        # Pagination
        offset = (page - 1) * page_size
        flows = query.offset(offset).limit(page_size).all()

        return flows, total

    def get_all_tags(self) -> List[dict]:
        """
        Collect all unique tags across all flows with their counts.
        Returns a list of {"name": ..., "count": ...} dicts sorted by count desc.
        """
        flows = self.db.query(HedgeFundFlow.tags).filter(
            HedgeFundFlow.tags.isnot(None)
        ).all()

        tag_counts: dict[str, int] = {}
        for (tags_value,) in flows:
            if tags_value is None:
                continue
            # tags_value may be a JSON string or already-parsed list depending on driver
            if isinstance(tags_value, str):
                try:
                    tags_list = json.loads(tags_value)
                except (json.JSONDecodeError, TypeError):
                    continue
            elif isinstance(tags_value, list):
                tags_list = tags_value
            else:
                continue

            for t in tags_list:
                if isinstance(t, str) and t.strip():
                    tag_counts[t] = tag_counts.get(t, 0) + 1

        return sorted(
            [{"name": name, "count": count} for name, count in tag_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )
    
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