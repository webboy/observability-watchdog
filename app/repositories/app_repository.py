"""Data access helpers for App entities."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.app import App
from app.schemas.app import AppCreate


class AppRepository:
    """Repository for monitored application CRUD operations."""

    @staticmethod
    def create(db: Session, payload: AppCreate) -> App:
        """Persist a new monitored application."""
        app = App(
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            environment=payload.environment,
        )
        db.add(app)
        db.commit()
        db.refresh(app)
        return app

    @staticmethod
    def get_by_id(db: Session, app_id: uuid.UUID) -> App | None:
        """Return an app by primary key."""
        return db.get(App, app_id)

    @staticmethod
    def get_by_slug(db: Session, slug: str) -> App | None:
        """Return an app by slug."""
        stmt = select(App).where(App.slug == slug)
        return db.scalar(stmt)

    @staticmethod
    def list_all(db: Session) -> list[App]:
        """Return all apps ordered by creation time."""
        stmt = select(App).order_by(App.created_at.asc())
        return list(db.scalars(stmt).all())

    @staticmethod
    def delete(db: Session, app: App) -> None:
        """Delete an app and cascade related records."""
        db.delete(app)
        db.commit()
