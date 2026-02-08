"""
LMS API Client for fetching course data.

This module handles communication with the LMS API to retrieve:
- Course information
- Course materials
- Video transcripts
"""

from typing import Any, cast

import httpx
from pydantic import BaseModel

from aegra_api.settings import settings  # type: ignore[import-untyped]


class CourseData(BaseModel):
    """Model for course data."""

    course_id: str
    title: str
    description: str | None = None
    levels: list[dict[str, Any]] = []


class MaterialData(BaseModel):
    """Model for course material."""

    material_id: str
    course_id: str
    title: str
    content: str
    type: str  # video, document, etc.
    metadata: dict[str, Any] = {}


class LMSClient:
    """Client for interacting with the LMS API."""

    def __init__(
        self,
        base_url: str | None = None,
        admin_token: str | None = None,
    ):
        """
        Initialize LMS client.

        Args:
            base_url: Base URL for the LMS API
            admin_token: Admin JWT token for authentication
        """
        self.base_url = base_url or settings.app.LMS_URL
        self.admin_token = admin_token or settings.app.ADMIN_TOKEN

        if not self.admin_token:
            raise ValueError("ADMIN_TOKEN is required for LMS API access")

        self.headers = {
            "Authorization": f"Bearer {self.admin_token}",
            "Content-Type": "application/json",
        }

    async def get_course(self, course_id: str) -> CourseData | None:
        """
        Fetch course data by ID.

        Args:
            course_id: The course ID to fetch

        Returns:
            CourseData object or None if not found
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/v1/courses/{course_id}",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                return CourseData(
                    course_id=course_id,
                    title=data.get("title", ""),
                    description=data.get("description"),
                    levels=data.get("levels", []),
                )
            except httpx.HTTPError as e:
                print(f"Error fetching course {course_id}: {e}")
                return None

    async def get_all_courses(self) -> list[CourseData]:
        """
        Fetch all available courses.

        Returns:
            List of CourseData objects
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/v1/courses",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                courses = []
                for course in data.get("courses", []):
                    courses.append(
                        CourseData(
                            course_id=course.get("_id", ""),
                            title=course.get("title", ""),
                            description=course.get("description"),
                            levels=course.get("levels", []),
                        )
                    )
                return courses
            except httpx.HTTPError as e:
                print(f"Error fetching courses: {e}")
                return []

    async def get_course_materials(self, course_id: str) -> list[MaterialData]:
        """
        Fetch all materials for a course.

        Args:
            course_id: The course ID

        Returns:
            List of MaterialData objects
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/v1/courses/{course_id}/materials",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                materials = []
                for material in data.get("materials", []):
                    materials.append(
                        MaterialData(
                            material_id=material.get("_id", ""),
                            course_id=course_id,
                            title=material.get("title", ""),
                            content=material.get("content", ""),
                            type=material.get("type", "document"),
                            metadata=material.get("metadata", {}),
                        )
                    )
                return materials
            except httpx.HTTPError as e:
                print(f"Error fetching materials for course {course_id}: {e}")
                return []

    async def get_lesson_details(
        self,
        course_id: str,
        level_title: str,
        module_index: int,
        lesson_index: int,
    ) -> dict[str, Any] | None:
        """
        Fetch lesson details including materials.

        Args:
            course_id: The course ID
            level_title: The level title
            module_index: The module index
            lesson_index: The lesson index

        Returns:
            Lesson data dictionary or None
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/v1/courses/{course_id}/{level_title}/modules/{module_index}/lessons/{lesson_index}",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
            except httpx.HTTPError as e:
                print(f"Error fetching lesson details: {e}")
                return None

    async def get_all_course_lessons(self, course_id: str) -> list[dict[str, Any]]:
        """
        Fetch all lessons for a course.

        Args:
            course_id: The course ID

        Returns:
            List of lesson data dictionaries
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/v1/courses/{course_id}/lessons",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = cast(dict[str, Any], response.json())
                return cast(list[dict[str, Any]], data.get("lessons", []))
            except httpx.HTTPError as e:
                print(f"Error fetching lessons for course {course_id}: {e}")
                return []
