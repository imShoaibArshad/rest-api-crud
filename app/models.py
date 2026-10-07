"""ORM model for the `books` resource."""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from . import db


def utcnow() -> datetime:
    """Timezone-aware now(). sqlite stores naive datetimes, so we normalise."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Book(db.Model):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    author: Mapped[str] = mapped_column(String(120), nullable=False)
    year: Mapped[int | None] = mapped_column()
    genre: Mapped[str | None] = mapped_column(String(60))
    rating: Mapped[float | None] = mapped_column()
    available: Mapped[bool] = mapped_column(default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("year IS NULL OR (year >= 1450 AND year <= 2100)", name="ck_book_year"),
        CheckConstraint("rating IS NULL OR (rating >= 0 AND rating <= 5)", name="ck_book_rating"),
        Index("ix_books_author", "author"),
        Index("ix_books_genre", "genre"),
    )

    def to_dict(self) -> dict:
        """Serialise explicitly rather than relying on a schema library —
        it keeps the API contract visible in one place."""
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "year": self.year,
            "genre": self.genre,
            "rating": self.rating,
            "available": self.available,
            "created_at": self.created_at.isoformat(timespec="seconds") + "Z",
            "updated_at": self.updated_at.isoformat(timespec="seconds") + "Z",
        }

    def apply(self, data: dict, partial: bool) -> None:
        """Set fields from a validated payload.

        PUT sends every required field (partial=False); PATCH sends only what
        changed (partial=True), so we must not blank out omitted columns.
        """
        for key, value in data.items():
            if key in ("created_at", "updated_at", "id"):
                continue
            setattr(self, key, value)
        if not partial:
            # PUT semantics: unspecified optional fields reset to their default,
            # matching RFC 7231's "request as a whole" reading of PUT.
            self.year = data.get("year", None)
            self.genre = data.get("genre", None)
            self.rating = data.get("rating", None)
            self.available = data.get("available", True)
