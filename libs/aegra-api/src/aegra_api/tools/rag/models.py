"""
Database models and schema for RAG vector storage.

This module defines the PostgreSQL tables for storing:
- Course content chunks
- Vector embeddings
- Metadata for retrieval
"""

from datetime import datetime

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text

from aegra_api.core.orm import Base


class CourseChunk(Base):
    """
    Table for storing chunked course content with embeddings.

    This table stores individual chunks of course content along with
    their vector embeddings for semantic search.
    """

    __tablename__ = "course_chunks"
    __table_args__ = (
        Index("idx_course_chunks_course_id", "course_id"),
        Index("idx_course_chunks_content_type", "content_type"),
        Index("idx_course_chunks_level", "course_id", "level_title"),
        # HNSW index for vector similarity search
        Index(
            "idx_course_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(String(255), nullable=False, index=True)
    chunk_id = Column(String(255), nullable=False, unique=True, index=True)

    # Content fields
    content = Column(Text, nullable=False)
    content_type = Column(
        String(50), nullable=False
    )  # course, lesson, material, transcript

    # Metadata
    title = Column(String(500))
    level_title = Column(String(255))
    module_index = Column(Integer)
    lesson_index = Column(Integer)
    material_id = Column(String(255))
    chunk_metadata = Column(
        JSON, default={}
    )  # Renamed from 'metadata' to avoid SQLAlchemy reserved name

    # Embedding vector (1536 dimensions for OpenAI text-embedding-3-small)
    embedding = Column(Vector(1536), nullable=False)

    # Chunking information
    chunk_index = Column(Integer, nullable=False)
    total_chunks = Column(Integer)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<CourseChunk(id={self.id}, course_id={self.course_id}, "
            f"title={self.title}, type={self.content_type})>"
        )


class IndexingStatus(Base):
    """
    Table for tracking indexing status of courses.

    This helps avoid re-indexing content that's already been processed.
    """

    __tablename__ = "indexing_status"
    __table_args__ = ({"extend_existing": True},)

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(String(255), nullable=False, unique=True, index=True)

    # Status tracking
    status = Column(
        String(50), nullable=False, default="pending"
    )  # pending, processing, completed, failed
    total_chunks = Column(Integer, default=0)
    indexed_chunks = Column(Integer, default=0)
    error_message = Column(Text)

    # Timestamps
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<IndexingStatus(course_id={self.course_id}, "
            f"status={self.status}, chunks={self.indexed_chunks}/{self.total_chunks})>"
        )
