"""
Text chunking utilities for RAG.

This module provides functions for chunking course content into
optimal sizes for embedding and retrieval.
"""

import httpx
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


class CourseContentChunker:
    """Chunker for course content using semantic-aware splitting."""

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 200,
    ):
        """
        Initialize the chunker.

        Args:
            chunk_size: Target size for each chunk (in characters)
            chunk_overlap: Overlap between chunks to maintain context
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Use recursive character splitter for better semantic chunking
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def chunk_text(
        self,
        text: str,
        metadata: dict | None = None,
    ) -> list[Document]:
        """
        Chunk text into Document objects.

        Args:
            text: Text to chunk
            metadata: Metadata to attach to each chunk

        Returns:
            List of Document objects with chunked content
        """
        if not text or not text.strip():
            return []

        metadata = metadata or {}

        # Create documents with metadata
        docs = self.text_splitter.create_documents(
            texts=[text],
            metadatas=[metadata],
        )

        return docs

    async def _fetch_transcript_from_url(self, url: str) -> str:
        """
        Fetch transcript content from a URL.

        Args:
            url: URL to the transcript file

        Returns:
            Transcript text content or empty string if fetch fails
        """
        if (
            not url
            or not isinstance(url, str)
            or not url.startswith(("http://", "https://"))
        ):
            return ""

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
                return response.text
        except Exception as e:
            print(f"⚠️  Failed to fetch transcript from {url}: {e}")
            return ""

    async def chunk_course_content(
        self,
        course_data: dict,
    ) -> list[dict]:
        """
        Chunk course content from various sources.

        Args:
            course_data: Dictionary containing course information

        Returns:
            List of chunk dictionaries with content and metadata
        """
        chunks = []

        # Extract and chunk course description
        if course_data.get("description"):
            desc_chunks = self.chunk_text(
                course_data["description"],
                metadata={
                    "content_type": "course_description",
                    "course_id": course_data.get("course_id"),
                    "title": course_data.get("title"),
                },
            )

            for idx, doc in enumerate(desc_chunks):
                chunks.append(
                    {
                        "content": doc.page_content,
                        "metadata": doc.metadata,
                        "chunk_index": idx,
                        "total_chunks": len(desc_chunks),
                    }
                )

        # Chunk lessons
        for lesson in course_data.get("lessons", []):
            # Try to get content from different possible fields
            lesson_content = None

            # Check for transcript field (video lessons)
            if lesson.get("transcript"):
                transcript = lesson["transcript"]
                # Check if it's a URL
                if isinstance(transcript, str) and transcript.startswith(
                    ("http://", "https://")
                ):
                    lesson_content = await self._fetch_transcript_from_url(transcript)
                elif isinstance(transcript, str) and transcript.strip():
                    lesson_content = transcript

            # Check for transcriptStructured field
            if not lesson_content and lesson.get("transcriptStructured"):
                structured = lesson["transcriptStructured"]
                if isinstance(structured, list):
                    texts = []
                    for item in structured:
                        if isinstance(item, dict):
                            # Try different possible text field names
                            text = (
                                item.get("text")
                                or item.get("content")
                                or item.get("transcript")
                                or ""
                            )
                            if text and str(text).strip():
                                # Check if text is a URL
                                if isinstance(text, str) and text.startswith(
                                    ("http://", "https://")
                                ):
                                    fetched_text = (
                                        await self._fetch_transcript_from_url(text)
                                    )
                                    if fetched_text:
                                        texts.append(fetched_text.strip())
                                else:
                                    texts.append(str(text).strip())
                        elif isinstance(item, str) and item.strip():
                            texts.append(item.strip())
                    lesson_content = " ".join(texts) if texts else None
                elif isinstance(structured, str):
                    # Check if it's a URL
                    if structured.startswith(("http://", "https://")):
                        lesson_content = await self._fetch_transcript_from_url(
                            structured
                        )
                    elif structured.strip():
                        lesson_content = structured
                elif isinstance(structured, dict):
                    # If it's a dict, try to get text from common fields
                    text = (
                        structured.get("text")
                        or structured.get("content")
                        or structured.get("transcript")
                        or ""
                    )
                    if text and isinstance(text, str):
                        if text.startswith(("http://", "https://")):
                            lesson_content = await self._fetch_transcript_from_url(text)
                        elif text.strip():
                            lesson_content = text

            # Fallback to content field if it exists
            if (
                not lesson_content
                and lesson.get("content")
                and str(lesson.get("content")).strip()
            ):
                lesson_content = lesson["content"]

            if lesson_content and str(lesson_content).strip():
                lesson_chunks = self.chunk_text(
                    str(lesson_content),
                    metadata={
                        "content_type": "lesson",
                        "course_id": course_data.get("course_id"),
                        "lesson_id": lesson.get("_id"),
                        "lesson_title": lesson.get("title"),
                        "level_title": lesson.get("levelTitle")
                        or lesson.get("level_title"),
                        "module_index": lesson.get("moduleIndex")
                        or lesson.get("module_index"),
                        "lesson_index": lesson.get("lessonIndex")
                        or lesson.get("lesson_index"),
                    },
                )

                for idx, doc in enumerate(lesson_chunks):
                    chunks.append(
                        {
                            "content": doc.page_content,
                            "metadata": doc.metadata,
                            "chunk_index": idx,
                            "total_chunks": len(lesson_chunks),
                        }
                    )

        # Chunk materials
        for material in course_data.get("materials", []):
            if material.get("content"):
                material_chunks = self.chunk_text(
                    material["content"],
                    metadata={
                        "content_type": "material",
                        "course_id": course_data.get("course_id"),
                        "material_id": material.get("_id"),
                        "material_title": material.get("title"),
                        "material_type": material.get("type"),
                    },
                )

                for idx, doc in enumerate(material_chunks):
                    chunks.append(
                        {
                            "content": doc.page_content,
                            "metadata": doc.metadata,
                            "chunk_index": idx,
                            "total_chunks": len(material_chunks),
                        }
                    )

        return chunks
