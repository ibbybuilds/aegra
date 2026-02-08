"""add_pgvector_rag_tables

Revision ID: e9f805444530
Revises: c22c266e4542
Create Date: 2025-10-31 16:41:06.712540

"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision = "e9f805444530"
down_revision = "c22c266e4542"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create course_chunks table
    op.create_table(
        "course_chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("course_id", sa.String(length=255), nullable=False),
        sa.Column("chunk_id", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("level_title", sa.String(length=255), nullable=True),
        sa.Column("module_index", sa.Integer(), nullable=True),
        sa.Column("lesson_index", sa.Integer(), nullable=True),
        sa.Column("material_id", sa.String(length=255), nullable=True),
        sa.Column("chunk_metadata", sa.JSON(), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_course_chunks_course_id", "course_chunks", ["course_id"])
    op.create_index("idx_course_chunks_content_type", "course_chunks", ["content_type"])
    op.create_index(
        "idx_course_chunks_level", "course_chunks", ["course_id", "level_title"]
    )
    op.create_index(
        "idx_course_chunks_chunk_id", "course_chunks", ["chunk_id"], unique=True
    )

    # Create HNSW index for vector similarity search
    op.execute(
        "CREATE INDEX idx_course_chunks_embedding_hnsw ON course_chunks "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # Create indexing_status table
    op.create_table(
        "indexing_status",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("course_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=True),
        sa.Column("indexed_chunks", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_indexing_status_course_id", "indexing_status", ["course_id"], unique=True
    )


def downgrade() -> None:
    # Drop indexing_status table
    op.drop_index("idx_indexing_status_course_id", table_name="indexing_status")
    op.drop_table("indexing_status")

    # Drop course_chunks table
    op.drop_index("idx_course_chunks_embedding_hnsw", table_name="course_chunks")
    op.drop_index("idx_course_chunks_chunk_id", table_name="course_chunks")
    op.drop_index("idx_course_chunks_level", table_name="course_chunks")
    op.drop_index("idx_course_chunks_content_type", table_name="course_chunks")
    op.drop_index("idx_course_chunks_course_id", table_name="course_chunks")
    op.drop_table("course_chunks")
