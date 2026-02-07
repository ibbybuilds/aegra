# RAG Course Retrieval System

This module provides Retrieval-Augmented Generation (RAG) capabilities for course content using PostgreSQL with pgvector extension.

## Features

- 🔍 **Semantic Search**: Find relevant course content using vector similarity
- 📚 **Course Indexing**: Index course descriptions, lessons, and materials
- 🧩 **Smart Chunking**: Intelligent text chunking with overlap for better context
- 🗄️ **PostgreSQL Storage**: Store embeddings in PostgreSQL with pgvector
- 🔧 **CLI Tool**: Easy-to-use command-line interface for indexing

## Environment Variables

The RAG system reads configuration directly from environment variables using `os.getenv()`:

- `DATABASE_URL`: PostgreSQL connection string (e.g., `postgresql+asyncpg://user:pass@host/db`)
- `LMS_URL`: LMS API base URL (e.g., `https://dedatahub-api.vercel.app`)
- `ADMIN_TOKEN`: JWT token for LMS API admin access
- `OPENAI_API_KEY`: OpenAI API key for generating embeddings

**Note:** Make sure these environment variables are set in your `.env` file and loaded by your shell or deployment environment before running any RAG commands.

## Architecture

### Components

1. **LMS Client** (`lms_client.py`): Fetches course data from the LMS API
2. **Chunker** (`chunker.py`): Splits content into optimal-sized chunks
3. **Course Retriever** (`course_retriever.py`): Handles embedding and retrieval
4. **Models** (`models.py`): Database schema for vector storage
5. **Ingest CLI** (`ingest.py`): Command-line tool for indexing

### Database Schema

#### `course_chunks` Table
- Stores individual chunks of course content
- Includes vector embeddings (1536 dimensions for OpenAI)
- Metadata for filtering and retrieval
- HNSW index for fast similarity search

#### `indexing_status` Table
- Tracks indexing progress for each course
- Prevents duplicate indexing
- Records errors and completion status

## Setup

### 1. Prerequisites

Ensure PostgreSQL has the pgvector extension enabled:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 2. Install Dependencies

The required packages are already in `pyproject.toml`:
- `langchain-openai`: OpenAI embeddings
- `pgvector`: PostgreSQL vector operations
- `psycopg[binary]`: PostgreSQL driver

### 3. Environment Variables

Set the following in your `.env` file:

```bash
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/aegra
OPENAI_API_KEY=sk-...
LMS_URL=https://dedatahub-api.vercel.app
ADMIN_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 4. Initialize Database

```bash
python -m aegra_api.tools.rag.ingest --init-db
```

## Usage

### Indexing Courses

#### Index a Single Course

```bash
python -m aegra_api.tools.rag.ingest --course-id <course_id>
```

Example:
```bash
python -m aegra_api.tools.rag.ingest --course-id 67890abcdef
```

#### Index All Courses

```bash
python -m aegra_api.tools.rag.ingest --all
```

This will:
1. Fetch all courses from the LMS API
2. Download course content, lessons, and materials
3. Chunk the content intelligently
4. Generate embeddings using OpenAI
5. Store in PostgreSQL with vector indexes

#### Check Indexing Status

```bash
python -m aegra_api.tools.rag.ingest --status <course_id>
```

### Using the Retriever in Code

```python
from aegra_api.tools.rag import CourseRetriever

# Initialize retriever
retriever = CourseRetriever()

# Search for relevant content
results = await retriever.search(
    query="What is machine learning?",
    course_id="67890abcdef",  # Optional: filter by course
    k=5  # Number of results
)

# Process results
for result in results:
    print(f"Title: {result['title']}")
    print(f"Content: {result['content']}")
    print(f"Type: {result['content_type']}")
    print("---")
```

## Chunking Strategy

Based on best practices from RAG research, we use:

- **Chunk Size**: 800 characters
- **Overlap**: 200 characters
- **Splitter**: Recursive character text splitter
- **Separators**: Paragraph breaks, newlines, sentences, spaces

This ensures:
- ✅ Chunks maintain semantic coherence
- ✅ Context is preserved across chunks
- ✅ Optimal balance between precision and recall
- ✅ Better retrieval accuracy

## Performance

### Vector Search

- Uses **HNSW (Hierarchical Navigable Small World)** index
- Parameters: `m=16`, `ef_construction=64`
- Distance metric: **Cosine similarity**
- Fast approximate nearest neighbor search

### Indexing Speed

- ~10 chunks per second (includes embedding generation)
- Batch commits every 10 chunks
- Progress tracking and error handling

## Error Handling

The system includes comprehensive error handling:

- ✅ Failed chunk indexing doesn't stop the entire process
- ✅ Indexing status tracked in database
- ✅ Detailed error messages for debugging
- ✅ Graceful handling of API failures
- ✅ Rollback on critical errors

## Integration with Agent

The retriever can be used as a tool in your LangGraph agent:

```python
from langchain.tools import tool

@tool
async def search_course_content(query: str, course_id: str = None) -> str:
    """Search for relevant course content."""
    retriever = CourseRetriever()
    results = await retriever.search(query, course_id=course_id, k=3)

    # Format results
    formatted = []
    for r in results:
        formatted.append(f"{r['title']}: {r['content']}")

    return "\n\n".join(formatted)
```

## Monitoring

Check indexing status at any time:

```bash
# View status for a specific course
python -m aegra_api.tools.rag.ingest --status <course_id>
```

This shows:
- Current status (pending, processing, completed, failed)
- Number of chunks indexed
- Start and completion times
- Error messages if any

## Best Practices

1. **Initial Indexing**: Run `--all` once to index all courses
2. **Incremental Updates**: Use `--course-id` for new/updated courses
3. **Monitoring**: Check status regularly to catch failures
4. **Re-indexing**: Safe to re-run - updates existing chunks
5. **API Limits**: Be mindful of OpenAI API rate limits

## Troubleshooting

### Database Connection Issues

Ensure pgvector extension is enabled:
```sql
SELECT * FROM pg_extension WHERE extname = 'vector';
```

### OpenAI API Errors

Check your API key and rate limits:
```bash
echo $OPENAI_API_KEY
```

### Missing Content

Verify the LMS API is accessible:
```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" $LMS_URL/api/v1/courses
```

## Future Enhancements

- [ ] Support for video transcript extraction
- [ ] Multi-modal embeddings (text + images)
- [ ] Hybrid search (keyword + semantic)
- [ ] Query expansion and reranking
- [ ] Caching for frequently accessed chunks
- [ ] Background job scheduling for auto-indexing

## References

- [RAG Techniques Repository](https://github.com/NirDiamant/RAG_TECHNIQUES)
- [LangChain pgvector Documentation](https://python.langchain.com/docs/integrations/vectorstores/pgvector)
- [pgvector Extension](https://github.com/pgvector/pgvector)
