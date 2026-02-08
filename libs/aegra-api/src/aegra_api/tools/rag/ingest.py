"""
CLI tool for indexing course content into the RAG vector database.

This script fetches course data from the LMS API and indexes it
for semantic search and retrieval.

Usage:
    python -m aegra_api.tools.rag.ingest --course-id <course_id>
    python -m aegra_api.tools.rag.ingest --all
    python -m aegra_api.tools.rag.ingest --status <course_id>
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv

from aegra_api.tools.rag.course_retriever import CourseRetriever
from aegra_api.tools.rag.lms_client import LMSClient

# Load .env from project root
project_root = Path(__file__).parent.parent.parent.parent.parent
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)


async def index_course(
    course_id: str,
    retriever: CourseRetriever,
    lms_client: LMSClient,
) -> bool:
    """
    Index a single course.

    Args:
        course_id: The course ID to index
        retriever: CourseRetriever instance
        lms_client: LMSClient instance

    Returns:
        True if successful, False otherwise
    """
    print(f"\n{'=' * 60}")
    print(f"📚 Indexing course: {course_id}")
    print(f"{'=' * 60}\n")

    # Fetch course data
    print("🔍 Fetching course data from LMS...")
    course = await lms_client.get_course(course_id)

    if not course:
        print(f"❌ Failed to fetch course {course_id}")
        return False

    print(f"✅ Fetched course: {course.title}")

    # Fetch lessons
    print("📖 Fetching lessons...")
    lessons = await lms_client.get_all_course_lessons(course_id)
    print(f"✅ Fetched {len(lessons)} lessons")

    # Fetch materials
    print("📄 Fetching materials...")
    materials = await lms_client.get_course_materials(course_id)
    print(f"✅ Fetched {len(materials)} materials")

    # Prepare course data
    course_data = {
        "course_id": course_id,
        "title": course.title,
        "description": course.description,
        "lessons": lessons,
        "materials": [
            {
                "_id": m.material_id,
                "title": m.title,
                "content": m.content,
                "type": m.type,
            }
            for m in materials
        ],
    }

    # Index the course
    result = await retriever.index_course(course_id, course_data)

    if result["status"] == "completed":
        print(f"\n✅ Successfully indexed course {course_id}")
        print(f"   Total chunks: {result['chunks']}")
        return True
    elif result["status"] == "already_indexed":
        print(f"\n⚠️  Course {course_id} was already indexed")
        print(f"   Total chunks: {result['chunks']}")
        return True
    else:
        print(f"\n❌ Failed to index course {course_id}")
        print(f"   Error: {result.get('error', 'Unknown error')}")
        return False


async def index_all_courses(
    retriever: CourseRetriever,
    lms_client: LMSClient,
) -> None:
    """
    Index all available courses.

    Args:
        retriever: CourseRetriever instance
        lms_client: LMSClient instance
    """
    print("\n{'='*60}")
    print("📚 Indexing ALL courses")
    print(f"{'=' * 60}\n")

    # Fetch all courses
    print("🔍 Fetching all courses from LMS...")
    courses = await lms_client.get_all_courses()

    if not courses:
        print("❌ No courses found")
        return

    print(f"✅ Found {len(courses)} courses\n")

    # Index each course
    success_count = 0
    failed_count = 0

    for idx, course in enumerate(courses, 1):
        print(f"\n[{idx}/{len(courses)}] Processing: {course.title}")

        success = await index_course(
            course.course_id,
            retriever,
            lms_client,
        )

        if success:
            success_count += 1
        else:
            failed_count += 1

    # Summary
    print(f"\n{'=' * 60}")
    print("📊 INDEXING SUMMARY")
    print(f"{'=' * 60}")
    print(f"✅ Successfully indexed: {success_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"📚 Total courses: {len(courses)}")
    print(f"{'=' * 60}\n")


def show_status(course_id: str, retriever: CourseRetriever) -> None:
    """
    Show indexing status for a course.

    Args:
        course_id: The course ID
        retriever: CourseRetriever instance
    """
    print(f"\n{'=' * 60}")
    print(f"📊 Indexing Status for: {course_id}")
    print(f"{'=' * 60}\n")

    status = retriever.get_indexing_status(course_id)

    if not status:
        print(f"⚠️  No indexing record found for course {course_id}")
        return

    print(f"Status: {status['status'].upper()}")
    print(f"Total chunks: {status['total_chunks']}")
    print(f"Indexed chunks: {status['indexed_chunks']}")

    if status["started_at"]:
        print(f"Started at: {status['started_at']}")

    if status["completed_at"]:
        print(f"Completed at: {status['completed_at']}")

    if status["error_message"]:
        print(f"\n❌ Error: {status['error_message']}")

    print(f"\n{'=' * 60}\n")


async def main() -> None:
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Index course content for RAG retrieval",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Index a specific course
  python -m aegra_api.tools.rag.ingest --course-id 12345

  # Index all courses
  python -m aegra_api.tools.rag.ingest --all

  # Check indexing status
  python -m aegra_api.tools.rag.ingest --status 12345
        """,
    )

    parser.add_argument(
        "--course-id",
        type=str,
        help="Index a specific course by ID",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Index all available courses",
    )

    parser.add_argument(
        "--status",
        type=str,
        help="Show indexing status for a course",
    )

    args = parser.parse_args()

    # Validate arguments
    if not any([args.course_id, args.all, args.status]):
        parser.print_help()
        sys.exit(1)

    # Initialize retriever
    print("\n🚀 Initializing RAG system...")
    retriever = CourseRetriever()

    # Handle status check
    if args.status:
        show_status(args.status, retriever)
        return

    # Initialize LMS client
    lms_client = LMSClient()

    # Handle indexing
    if args.all:
        await index_all_courses(retriever, lms_client)
    elif args.course_id:
        await index_course(args.course_id, retriever, lms_client)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Indexing interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
