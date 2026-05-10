import pytest

from tests.e2e._utils import get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_assistant_count():
    """
    Test that multiple assistants with different metadata and contexts
    can be created and counted correctly.
    """
    client = get_e2e_client()

    # Keep track of created assistants for cleanup
    created_assistants = []

    try:
        # 1. Create assistants with varying metadata and contexts
        assistants_to_create = [
            {
                "name": "A1",
                "metadata": {"type": "alpha"},
                "context": {"max_search_results": 1},
            },
            {
                "name": "A2",
                "metadata": {"type": "beta"},
                "context": {"max_search_results": 2},
            },
            {
                "name": "A3",
                "metadata": {"type": "alpha"},
                "context": {"max_search_results": 3},
            },
            {
                "name": "A4",
                "metadata": {"type": "gamma"},
                "context": {"max_search_results": 4},
            },
            {
                "name": "A5",
                "metadata": {"type": "beta"},
                "context": {"max_search_results": 5},
            },
        ]

        for spec in assistants_to_create:
            assistant = await client.assistants.create(
                name=spec["name"],
                description=f"{spec['name']} Assistant",
                graph_id="agent",
                context=spec["context"],
                metadata=spec["metadata"],
                if_exists="do_nothing",
            )
            created_assistants.append(assistant)

        # 2. Run counts and validate
        count_alpha = await client.assistants.count(metadata={"type": "alpha"})
        assert count_alpha == 2, f"Expected 2 results, got {count_alpha}"

        count_beta = await client.assistants.count(metadata={"type": "beta"})
        assert count_beta == 2, f"Expected 2 results, got {count_beta}"

        count_gamma = await client.assistants.count(metadata={"type": "gamma"})
        assert count_gamma == 1, f"Expected 1 result, got {count_gamma}"

        count_all = await client.assistants.count()
        assert count_all >= 5, f"Expected at least 5 results, got {count_all}"

    finally:
        # 3. Cleanup all assistants
        for assistant in created_assistants:
            await client.assistants.delete(assistant_id=assistant["assistant_id"])


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_assistant_search_metadata():
    """
    Test that multiple assistants with different metadata and contexts
    can be created and searched correctly.
    """
    client = get_e2e_client()

    # Keep track of created assistants for cleanup
    created_assistants = []

    try:
        # 1. Create assistants with varying metadata and contexts
        assistants_to_create = [
            {
                "name": "A1",
                "metadata": {"category": "test", "group": "1"},
                "context": {"max_search_results": 1},
            },
            {
                "name": "A2",
                "metadata": {"category": "test", "group": "2"},
                "context": {"max_search_results": 2},
            },
            {
                "name": "A3",
                "metadata": {"category": "dev", "group": "1"},
                "context": {"max_search_results": 3},
            },
            {
                "name": "A4",
                "metadata": {"category": "prod", "group": "3"},
                "context": {"max_search_results": 4},
            },
            {
                "name": "A5",
                "metadata": {"category": "test", "group": "1"},
                "context": {"max_search_results": 5},
            },
        ]

        for spec in assistants_to_create:
            assistant = await client.assistants.create(
                name=spec["name"],
                description=f"{spec['name']} Assistant",
                graph_id="agent",
                context=spec["context"],
                metadata=spec["metadata"],
                if_exists="do_nothing",
            )
            created_assistants.append(assistant)

        # 2. Run searches and validate counts
        search_test = await client.assistants.search(metadata={"category": "test"})
        assert len(search_test) == 3, f"Expected 3 results, got {len(search_test)}"

        search_dev = await client.assistants.search(metadata={"category": "dev"})
        assert len(search_dev) == 1, f"Expected 1 result, got {len(search_dev)}"

        search_prod = await client.assistants.search(metadata={"category": "prod"})
        assert len(search_prod) == 1, f"Expected 1 result, got {len(search_prod)}"

        search_test_group1 = await client.assistants.search(metadata={"category": "test", "group": "1"})
        assert len(search_test_group1) == 2, f"Expected 2 results, got {len(search_test_group1)}"

        search_test_group2 = await client.assistants.search(metadata={"category": "test", "group": "2"})
        assert len(search_test_group2) == 1, f"Expected 1 result, got {len(search_test_group2)}"

        search_nonexistent = await client.assistants.search(metadata={"category": "staging"})
        assert len(search_nonexistent) == 0, f"Expected 0 results, got {len(search_nonexistent)}"

    finally:
        # 3. Cleanup all assistants
        for assistant in created_assistants:
            await client.assistants.delete(assistant_id=assistant["assistant_id"])


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_assistant_search_sort_by_name_asc():
    """Sort_by=name + sort_order=asc returns lexicographically ascending names."""
    client = get_e2e_client()
    created = []
    try:
        for i, name in enumerate(("zeta-sort-asst", "alpha-sort-asst", "mu-sort-asst")):
            a = await client.assistants.create(
                name=name,
                graph_id="agent",
                context={"max_search_results": i + 100},
                metadata={"sort_test_marker": "asc-name"},
                if_exists="do_nothing",
            )
            created.append(a)

        results = await client.assistants.search(
            metadata={"sort_test_marker": "asc-name"},
            sort_by="name",
            sort_order="asc",
        )

        names = [r["name"] for r in results]
        assert names == sorted(names), f"Expected ascending order, got {names}"
    finally:
        for a in created:
            await client.assistants.delete(assistant_id=a["assistant_id"])


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_assistant_search_sort_by_name_desc():
    """Sort_by=name + sort_order=desc returns lexicographically descending names."""
    client = get_e2e_client()
    created = []
    try:
        for i, name in enumerate(("alpha-sort-d", "zeta-sort-d", "mu-sort-d")):
            a = await client.assistants.create(
                name=name,
                graph_id="agent",
                context={"max_search_results": i + 200},
                metadata={"sort_test_marker": "desc-name"},
                if_exists="do_nothing",
            )
            created.append(a)

        results = await client.assistants.search(
            metadata={"sort_test_marker": "desc-name"},
            sort_by="name",
            sort_order="desc",
        )

        names = [r["name"] for r in results]
        assert names == sorted(names, reverse=True), f"Expected descending order, got {names}"
    finally:
        for a in created:
            await client.assistants.delete(assistant_id=a["assistant_id"])


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_assistant_search_pagination_is_stable_across_offset():
    """Tie-break on assistant_id keeps offset pagination stable when many rows
    share a sort key (e.g. created in the same microsecond batch)."""
    client = get_e2e_client()
    created = []
    try:
        for i in range(5):
            a = await client.assistants.create(
                name=f"pagestable-{i}",
                graph_id="agent",
                context={"max_search_results": i + 300},
                metadata={"sort_test_marker": "pagination"},
                if_exists="do_nothing",
            )
            created.append(a)

        page_one = await client.assistants.search(
            metadata={"sort_test_marker": "pagination"},
            limit=2,
            offset=0,
        )
        page_two = await client.assistants.search(
            metadata={"sort_test_marker": "pagination"},
            limit=2,
            offset=2,
        )

        page_one_ids = {a["assistant_id"] for a in page_one}
        page_two_ids = {a["assistant_id"] for a in page_two}
        assert not page_one_ids & page_two_ids, "Pagination pages overlap (tie-break missing)"
    finally:
        for a in created:
            await client.assistants.delete(assistant_id=a["assistant_id"])
