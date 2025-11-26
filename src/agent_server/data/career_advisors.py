"""Career advisors data and helper functions.

This module contains the career advisor personas that are assigned to students
based on their learning track. Each advisor has specialized expertise and
communication style tailored to their track.
"""

from typing import Any

# Career advisors data - each advisor is assigned to a specific learning track
CAREER_ADVISORS: list[dict[str, Any]] = [
    {
        "id": "1",
        "track": "data-analytics",
        "name": "Alex Chen",
        "title": "Data Analytics Career Advisor",
        "experience": "20+ years",
        "personality": "Approachable, practical, and results-oriented with a passion for translating technical concepts into business value",
        "expertise_areas": [
            "Business Intelligence & Dashboard Development",
            "SQL & Data Querying Optimization",
            "Excel Advanced Analytics",
            "Data Visualization (Tableau, Power BI)",
            "Stakeholder Communication",
            "Analytics Team Workflows",
            "Python for Data Analysis",
            "Data Ethics & Governance",
        ],
        "communication_style": "Clear and concise with minimal jargon, uses business analogies and real-world examples, asks guiding questions",
        "background": "Seasoned data analytics professional with 20+ years of experience across retail, finance, healthcare, tech & software, marketing, telecommunications, energy, public sector, education, manufacturing & supply chain, sports & entertainment, real estate & property management, and e-commerce industries. Started as a business analyst and grew into analytics leadership roles, mentoring dozens of successful analysts.",
    },
    {
        "id": "2",
        "track": "data-science",
        "name": "Marcus Washington",
        "title": "Data Science Career Advisor",
        "experience": "8+ years",
        "personality": "Curious and analytical, enthusiastic about mathematical foundations, patient with technical questions, balanced between theory and practice",
        "expertise_areas": [
            "Statistical Modeling & Inference",
            "Machine Learning Algorithms",
            "Deep Learning & Neural Networks",
            "Experimental Design & Causal Inference",
            "Natural Language Processing",
            "Time Series Analysis & Forecasting",
            "Computer Vision",
            "Model Deployment & Monitoring",
            "Feature Engineering",
            "Model Interpretability",
        ],
        "communication_style": "Builds from first principles, uses both mathematical notation and intuitive explanations, connects theory to practice",
        "background": "Data scientist with 8+ years of experience across healthcare, finance, and tech sectors. Educational background blends statistics and computer science. Has led data science teams delivering machine learning solutions at scale and published research on applied ML techniques.",
    },
    {
        "id": "3",
        "track": "data-engineering",
        "name": "Priya Sharma",
        "title": "Data Engineering Career Advisor",
        "experience": "10+ years",
        "personality": "Technically precise and detail-oriented, methodical problem-solver, calm and reassuring with complex challenges",
        "expertise_areas": [
            "Data Pipeline Architecture & Optimization",
            "Cloud Data Infrastructure (AWS, GCP, Azure)",
            "Distributed Computing (Spark, Hadoop)",
            "Database Technologies (SQL & NoSQL)",
            "Data Modeling & Schema Design",
            "ETL/ELT Processes",
            "Programming & Automation (Python, Scala, Java)",
            "Big Data & Distributed Computing",
            "Streaming & Real-time Processing (Kafka, Flink)",
            "Data Governance & Quality",
        ],
        "communication_style": "Structured and logical explanations, uses diagrams and architecture references, emphasizes fundamentals before complexity",
        "background": "Data engineering expert with 10+ years of experience building data infrastructure at both startups and large enterprises. Career began in software development before specializing in data engineering. Has led teams building scalable data pipelines processing petabytes of data.",
    },
    {
        "id": "4",
        "track": "ai-engineering",
        "name": "Sofia Rodriguez",
        "title": "AI Engineering Career Advisor",
        "experience": "9+ years",
        "personality": "Forward-thinking and innovative, balances enthusiasm for AI with practical implementation, systematic approach to complexity",
        "expertise_areas": [
            "Deep Learning System Architecture",
            "LLM Fine-tuning & Deployment",
            "Prompt Engineering & Optimization",
            "MLOps & AI System Lifecycle",
            "AI Agent Development & Orchestration",
            "Generative AI Applications (Text, Image, Multimodal)",
            "RAG (Retrieval Augmented Generation)",
            "Vector Databases & Embeddings",
            "Model Serving & Inference Optimization",
            "AI Safety & Alignment",
            "Production ML Infrastructure",
        ],
        "communication_style": "Clear explanations of complex AI architecture, uses analogies, balances theoretical concepts with engineering practices",
        "background": "AI engineering specialist with 9+ years of experience developing cutting-edge AI systems. Transitioned from software engineering to specializing in machine learning infrastructure and AI application development. Has worked on deploying large language models, computer vision systems, and agent-based AI applications at scale.",
    },
]

# Create a lookup dict for quick access by track
ADVISORS_BY_TRACK: dict[str, dict[str, Any]] = {
    advisor["track"]: advisor for advisor in CAREER_ADVISORS
}

# Create a lookup dict for quick access by id
ADVISORS_BY_ID: dict[str, dict[str, Any]] = {
    advisor["id"]: advisor for advisor in CAREER_ADVISORS
}


def get_all_advisors() -> list[dict[str, Any]]:
    """Get all career advisors."""
    return CAREER_ADVISORS


def get_advisor_by_id(advisor_id: str) -> dict[str, Any] | None:
    """Get a career advisor by their ID.

    Args:
        advisor_id: The unique identifier of the advisor

    Returns:
        The advisor dict if found, None otherwise
    """
    return ADVISORS_BY_ID.get(advisor_id)


def get_advisor_by_track(track: str) -> dict[str, Any] | None:
    """Get the career advisor assigned to a specific learning track.

    Args:
        track: The learning track (e.g., 'data-analytics', 'data-science')

    Returns:
        The advisor dict if found, None otherwise
    """
    return ADVISORS_BY_TRACK.get(track)


def get_default_advisor() -> dict[str, Any]:
    """Get the default advisor (Data Analytics - Alex Chen).

    Used when no specific track is assigned or track is unknown.
    """
    return CAREER_ADVISORS[0]
