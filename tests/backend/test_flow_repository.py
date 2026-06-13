"""Unit tests for FlowRepository.query_flows (filter / search / tag / sort / paginate).

Uses an in-memory SQLite database so no application DB is required.
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend.database.connection import Base
from app.backend.database.models import HedgeFundFlow
from app.backend.repositories.flow_repository import FlowRepository


@pytest.fixture
def repo():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    _seed(session)
    try:
        yield FlowRepository(session)
    finally:
        session.close()
        engine.dispose()


def _add(session, *, name, description, is_template, tags, created, updated):
    session.add(
        HedgeFundFlow(
            name=name,
            description=description,
            nodes=[],
            edges=[],
            is_template=is_template,
            tags=tags,
            created_at=created,
            updated_at=updated,
        )
    )


def _seed(session):
    # created/updated chosen so COALESCE(updated_at, created_at) desc => D, A, B, E (non-templates)
    _add(session, name="Alpha Growth", description="value investing", is_template=False,
         tags=["growth", "value"], created=datetime(2024, 1, 1), updated=datetime(2024, 3, 10))
    _add(session, name="Beta Momentum", description="trend following", is_template=False,
         tags=["momentum"], created=datetime(2024, 1, 2), updated=datetime(2024, 3, 5))
    _add(session, name="Gamma Template", description="reusable base", is_template=True,
         tags=["template", "growth"], created=datetime(2024, 1, 3), updated=datetime(2024, 3, 20))
    # never updated -> updated_at is NULL; coalesce should fall back to created_at (newest here)
    _add(session, name="Delta Fresh", description=None, is_template=False,
         tags=None, created=datetime(2024, 3, 25), updated=None)
    _add(session, name="Epsilon", description="growth story", is_template=False,
         tags=[], created=datetime(2024, 1, 5), updated=datetime(2024, 2, 1))
    session.commit()


def _names(items):
    return [f.name for f in items]


def test_no_filters_returns_all(repo):
    items, total = repo.query_flows(limit=100)
    assert total == 5
    assert len(items) == 5


def test_is_template_tristate(repo):
    templates, t_total = repo.query_flows(is_template=True, limit=100)
    assert t_total == 1
    assert _names(templates) == ["Gamma Template"]

    non_templates, n_total = repo.query_flows(is_template=False, limit=100)
    assert n_total == 4
    assert set(_names(non_templates)) == {"Alpha Growth", "Beta Momentum", "Delta Fresh", "Epsilon"}


def test_keyword_matches_name_description_and_tags(repo):
    # "growth": name (Alpha Growth) + tag (Gamma Template) + description (Epsilon "growth story")
    items, total = repo.query_flows(keyword="growth", limit=100)
    assert total == 3
    assert set(_names(items)) == {"Alpha Growth", "Gamma Template", "Epsilon"}

    # name-only match
    items, total = repo.query_flows(keyword="momentum", limit=100)
    assert set(_names(items)) == {"Beta Momentum"}

    # description-only match
    items, total = repo.query_flows(keyword="reusable", limit=100)
    assert set(_names(items)) == {"Gamma Template"}


def test_tags_exact_membership_or_semantics(repo):
    items, total = repo.query_flows(tags=["growth"], limit=100)
    assert total == 2
    assert set(_names(items)) == {"Alpha Growth", "Gamma Template"}

    # OR across multiple tags
    items, total = repo.query_flows(tags=["momentum", "value"], limit=100)
    assert set(_names(items)) == {"Alpha Growth", "Beta Momentum"}

    # exact match, not substring (no flow has tag "grow")
    items, total = repo.query_flows(tags=["grow"], limit=100)
    assert total == 0


def test_sort_desc_uses_coalesced_update_time(repo):
    items, total = repo.query_flows(is_template=False, sort_order="desc", limit=100)
    # Delta Fresh has NULL updated_at but newest created_at -> should sort first
    assert _names(items) == ["Delta Fresh", "Alpha Growth", "Beta Momentum", "Epsilon"]


def test_sort_asc(repo):
    items, _ = repo.query_flows(is_template=False, sort_order="asc", limit=100)
    assert _names(items) == ["Epsilon", "Beta Momentum", "Alpha Growth", "Delta Fresh"]


def test_pagination_returns_total_and_page(repo):
    page1, total = repo.query_flows(is_template=False, sort_order="desc", limit=2, offset=0)
    assert total == 4
    assert _names(page1) == ["Delta Fresh", "Alpha Growth"]

    page2, total = repo.query_flows(is_template=False, sort_order="desc", limit=2, offset=2)
    assert total == 4
    assert _names(page2) == ["Beta Momentum", "Epsilon"]
