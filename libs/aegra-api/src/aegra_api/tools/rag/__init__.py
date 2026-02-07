"""
RAG (Retrieval-Augmented Generation) tools for fetching course information.

This module provides tools for:
- Fetching and indexing course materials
- Semantic search over course content
- Retrieving relevant information based on user queries
"""

from aegra_api.tools.rag.course_retriever import CourseRetriever, setup_rag_tool

__all__ = ["CourseRetriever", "setup_rag_tool"]
