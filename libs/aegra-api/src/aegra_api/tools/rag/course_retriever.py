"""
Course retriever using PostgreSQL with pgvector for semantic search.

This module provides the main RAG functionality for retrieving
relevant course information based on semantic similarity.
"""

import hashlib
from datetime import datetime
from typing import Any

from langchain_openai import OpenAIEmbeddings
from sqlalchemy import and_, create_engine, select
from sqlalchemy.orm import sessionmaker

from aegra_api.core.orm import Base  # type: ignore
from aegra_api.settings import settings  # type: ignore[import-untyped]
from aegra_api.tools.rag.chunker import CourseContentChunker  # type: ignore[import-untyped]
from aegra_api.tools.rag.models import CourseChunk, IndexingStatus  # type: ignore[import-untyped]


class CourseRetriever:
    """Retriever for course content using vector similarity search."""

    def __init__(
        self,
        database_url: str | None = None,
        embedding_model: str = "text-embedding-3-small",
    ):
        """
        Initialize the course retriever.

        Args:
            database_url: PostgreSQL connection string
            embedding_model: OpenAI embedding model to use
        """
        self.database_url = database_url or settings.db.database_url
        if not self.database_url:
            raise ValueError("DATABASE_URL is required")

        # Convert asyncpg URL to psycopg (for pgvector compatibility)
        if "asyncpg" in self.database_url:
            self.database_url = self.database_url.replace(
                "postgresql+asyncpg://", "postgresql+psycopg://"
            )

        self.engine = create_engine(self.database_url)
        self.Session = sessionmaker(bind=self.engine)

        # Initialize embeddings
        self.embeddings = OpenAIEmbeddings(model=embedding_model)

        # Initialize chunker
        self.chunker = CourseContentChunker()

    def initialize_schema(self) -> None:
        """Initialize database schema."""
        Base.metadata.create_all(self.engine)

    def _generate_chunk_id(
        self,
        course_id: str,
        content: str,
        chunk_index: int,
    ) -> str:
        """Generate a unique ID for a chunk."""
        content_hash = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[
            :8
        ]
        return f"{course_id}_{chunk_index}_{content_hash}"

    async def index_course(
        self,
        course_id: str,
        course_data: dict,
    ) -> dict[str, Any]:
        """
        Index a course's content for retrieval.

        Args:
            course_id: The course ID
            course_data: Dictionary containing course information

        Returns:
            Dictionary with indexing results
        """
        session = self.Session()

        try:
            # Check if already indexed
            status = (
                session.query(IndexingStatus).filter_by(course_id=course_id).first()
            )

            if status and status.status == "completed":
                print(f"⚠️  Course {course_id} already indexed")
                return {
                    "course_id": course_id,
                    "status": "already_indexed",
                    "chunks": status.total_chunks,
                }

            # Create or update status
            if not status:
                status = IndexingStatus(
                    course_id=course_id,
                    status="processing",
                    started_at=datetime.utcnow(),
                )
                session.add(status)
            else:
                status.status = "processing"  # type: ignore[assignment]
                status.started_at = datetime.utcnow()  # type: ignore[assignment]
                status.error_message = None  # type: ignore[assignment]

            session.commit()

            # Chunk the content
            print(f"📝 Chunking content for course {course_id}...")
            chunks = await self.chunker.chunk_course_content(course_data)

            if not chunks:
                status.status = "failed"  # type: ignore[assignment]
                status.error_message = "No content to index"  # type: ignore[assignment]
                session.commit()
                return {
                    "course_id": course_id,
                    "status": "failed",
                    "error": "No content to index",
                }

            status.total_chunks = len(chunks)  # type: ignore[assignment]
            session.commit()

            # Generate embeddings and store
            print(f"🔢 Generating embeddings for {len(chunks)} chunks...")
            indexed_count = 0

            for chunk_data in chunks:
                try:
                    # Generate embedding
                    embedding = await self.embeddings.aembed_query(
                        chunk_data["content"]
                    )

                    # Generate chunk ID
                    chunk_id = self._generate_chunk_id(
                        course_id,
                        chunk_data["content"],
                        chunk_data["chunk_index"],
                    )

                    # Check if chunk already exists
                    existing = (
                        session.query(CourseChunk).filter_by(chunk_id=chunk_id).first()
                    )

                    if existing:
                        # Update existing chunk
                        existing.content = chunk_data["content"]  # type: ignore[assignment]
                        existing.embedding = embedding  # type: ignore[assignment]
                        existing.chunk_metadata = chunk_data["metadata"]  # type: ignore[assignment]
                        existing.updated_at = datetime.utcnow()  # type: ignore[assignment]
                    else:
                        # Create new chunk
                        chunk = CourseChunk(
                            course_id=course_id,
                            chunk_id=chunk_id,
                            content=chunk_data["content"],
                            content_type=chunk_data["metadata"].get(
                                "content_type", "unknown"
                            ),
                            title=chunk_data["metadata"].get("title")
                            or chunk_data["metadata"].get("lesson_title")
                            or chunk_data["metadata"].get("material_title"),
                            level_title=chunk_data["metadata"].get("level_title"),
                            module_index=chunk_data["metadata"].get("module_index"),
                            lesson_index=chunk_data["metadata"].get("lesson_index"),
                            material_id=chunk_data["metadata"].get("material_id"),
                            chunk_metadata=chunk_data["metadata"],
                            embedding=embedding,
                            chunk_index=chunk_data["chunk_index"],
                            total_chunks=chunk_data["total_chunks"],
                        )
                        session.add(chunk)

                    indexed_count += 1
                    status.indexed_chunks = indexed_count  # type: ignore[assignment]

                    # Commit in batches
                    if indexed_count % 10 == 0:
                        session.commit()
                        print(f"  ✓ Indexed {indexed_count}/{len(chunks)} chunks")

                except Exception as e:
                    print(f"  ✗ Error indexing chunk: {e}")
                    continue

            # Final commit
            session.commit()

            # Update status
            status.status = "completed"  # type: ignore[assignment]
            status.completed_at = datetime.utcnow()  # type: ignore[assignment]
            session.commit()

            print(
                f"✅ Successfully indexed {indexed_count} chunks for course {course_id}"
            )

            return {
                "course_id": course_id,
                "status": "completed",
                "chunks": indexed_count,
            }

        except Exception as e:
            session.rollback()
            print(f"❌ Error indexing course {course_id}: {e}")

            # Update status
            if status:
                status.status = "failed"  # type: ignore[assignment]
                status.error_message = str(e)  # type: ignore[assignment]
                session.commit()

            return {
                "course_id": course_id,
                "status": "failed",
                "error": str(e),
            }

        finally:
            session.close()

    async def search(
        self,
        query: str,
        course_id: str | None = None,
        content_type: str | None = None,
        k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Search for relevant course content.

        Args:
            query: Search query
            course_id: Optional course ID to filter by
            content_type: Optional content type to filter by
            k: Number of results to return

        Returns:
            List of relevant chunks with metadata
        """
        session = self.Session()

        try:
            # Generate query embedding
            query_embedding = await self.embeddings.aembed_query(query)

            # Build query
            filters = []
            if course_id:
                filters.append(CourseChunk.course_id == course_id)
            if content_type:
                filters.append(CourseChunk.content_type == content_type)

            # Vector similarity search using cosine distance
            query_obj = (
                select(CourseChunk)
                .order_by(CourseChunk.embedding.cosine_distance(query_embedding))
                .limit(k)
            )

            if filters:
                query_obj = query_obj.where(and_(*filters))

            results = session.execute(query_obj).scalars().all()

            # Format results
            formatted_results = []
            for chunk in results:
                formatted_results.append(
                    {
                        "content": chunk.content,
                        "course_id": chunk.course_id,
                        "title": chunk.title,
                        "content_type": chunk.content_type,
                        "level_title": chunk.level_title,
                        "metadata": chunk.chunk_metadata,
                    }
                )

            return formatted_results

        finally:
            session.close()

    def get_indexing_status(self, course_id: str) -> dict[str, Any] | None:
        """Get indexing status for a course."""
        session = self.Session()

        try:
            status = (
                session.query(IndexingStatus).filter_by(course_id=course_id).first()
            )

            if not status:
                return None

            return {
                "course_id": status.course_id,
                "status": status.status,
                "total_chunks": status.total_chunks,
                "indexed_chunks": status.indexed_chunks,
                "started_at": status.started_at.isoformat()
                if status.started_at
                else None,
                "completed_at": status.completed_at.isoformat()
                if status.completed_at
                else None,
                "error_message": status.error_message,
            }

        finally:
            session.close()


def setup_rag_tool() -> CourseRetriever:
    """Setup function to initialize RAG components."""
    retriever = CourseRetriever()
    retriever.initialize_schema()
    return retriever
