#!/usr/bin/env python3
"""Populate the database with test data for UI development.

Usage:
    uv run scripts/populate_test_data.py          # Default: 365 days, 200 workflows
    uv run scripts/populate_test_data.py --days 30 --workflows 50
    uv run scripts/populate_test_data.py --help

To clean up, simply delete the database:
    rm ~/.amelia/amelia.db
"""

import argparse
import asyncio
import json
import random

# Add parent to path for imports
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4


sys.path.insert(0, str(Path(__file__).parent.parent))

from amelia.server.config import ServerConfig
from amelia.server.database.connection import Database
from amelia.server.models.tokens import MODEL_PRICING, TokenUsage


@dataclass
class WorkflowData:
    """Simple workflow data container for test data generation."""

    id: str
    issue_id: str
    worktree_path: str
    workflow_status: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_reason: str | None

# Realistic issue IDs
ISSUE_PREFIXES = ["PROJ", "BUG", "FEAT", "TASK", "SPIKE"]

# Multi-provider model selection
# Includes Anthropic Claude 4.5, OpenAI, Google, DeepSeek, Mistral, Qwen, and MiniMax
MODELS = [
    # Anthropic Claude 4.5 (primary - 40% total)
    ("claude-sonnet-4-5-20251101", 0.20),  # Primary workhorse
    ("claude-haiku-4-5-20251101", 0.12),   # Fast/cheap tasks
    ("claude-opus-4-5-20251101", 0.08),    # Complex reasoning
    # OpenAI (20% total)
    ("openai/gpt-4o", 0.12),               # GPT-4o - versatile
    ("openai/o3-mini", 0.05),              # o3-mini - efficient reasoning
    ("openai/o1", 0.03),                   # o1 - advanced reasoning
    # Google Gemini (10% total)
    ("google/gemini-2.0-flash", 0.06),     # Fast and cheap
    ("google/gemini-2.0-pro", 0.04),       # Higher capability
    # DeepSeek (10% total) - Very cost-effective
    ("deepseek/deepseek-coder-v3", 0.06),  # Coding specialist
    ("deepseek/deepseek-v3", 0.04),        # General purpose
    # Mistral (5% total)
    ("mistral/codestral-latest", 0.05),   # Coding specialist
    # Qwen (10% total) - Open source
    ("qwen/qwen-2.5-coder-32b", 0.06),     # Coding specialist
    ("qwen/qwen-2.5-72b", 0.04),           # General purpose
    # MiniMax (5% total)
    ("minimax/minimax-m2", 0.03),          # Compact, efficient
    ("minimax/minimax-m1", 0.02),          # Long context
]

# Agents that produce token usage
AGENTS = ["architect", "developer", "reviewer"]

# Workflow statuses and their weights
WORKFLOW_STATUSES = [
    ("completed", 0.6),
    ("failed", 0.15),
    ("cancelled", 0.1),
    ("in_progress", 0.1),
    ("blocked", 0.05),
]


def weighted_choice(choices: list[tuple[str, float]]) -> str:
    """Select from weighted choices."""
    items, weights = zip(*choices, strict=False)
    result: str = random.choices(items, weights=weights, k=1)[0]
    return result


def random_issue_id() -> str:
    """Generate a random issue ID."""
    prefix = random.choice(ISSUE_PREFIXES)
    number = random.randint(100, 9999)
    return f"{prefix}-{number}"


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_creation_tokens: int,
) -> float:
    """Calculate cost based on model pricing."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["sonnet"])

    # Base input tokens (excluding cache reads, which are cheaper)
    base_input = input_tokens - cache_read_tokens

    cost = (
        (base_input * pricing["input"] / 1_000_000)
        + (cache_read_tokens * pricing["cache_read"] / 1_000_000)
        + (cache_creation_tokens * pricing["cache_write"] / 1_000_000)
        + (output_tokens * pricing["output"] / 1_000_000)
    )
    return round(cost, 6)


def generate_token_usage(
    workflow_id: str,
    agent: str,
    timestamp: datetime,
    model: str,
) -> TokenUsage:
    """Generate realistic token usage for an agent."""
    # Architect tends to have larger inputs (reading codebase), smaller outputs
    # Developer has medium input/output with many turns
    # Reviewer has smaller interactions

    if agent == "architect":
        input_tokens = random.randint(50000, 150000)
        output_tokens = random.randint(2000, 8000)
        cache_read_ratio = random.uniform(0.3, 0.7)
        num_turns = random.randint(1, 3)
        duration_ms = random.randint(30000, 120000)
    elif agent == "developer":
        input_tokens = random.randint(100000, 500000)
        output_tokens = random.randint(10000, 50000)
        cache_read_ratio = random.uniform(0.4, 0.8)
        num_turns = random.randint(5, 30)
        duration_ms = random.randint(60000, 600000)
    else:  # reviewer
        input_tokens = random.randint(30000, 100000)
        output_tokens = random.randint(1000, 5000)
        cache_read_ratio = random.uniform(0.5, 0.9)
        num_turns = random.randint(1, 5)
        duration_ms = random.randint(20000, 90000)

    cache_read_tokens = int(input_tokens * cache_read_ratio)
    cache_creation_tokens = int(input_tokens * random.uniform(0.1, 0.3))

    cost = calculate_cost(
        model,
        input_tokens,
        output_tokens,
        cache_read_tokens,
        cache_creation_tokens,
    )

    return TokenUsage(
        id=str(uuid4()),
        workflow_id=workflow_id,
        agent=agent,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cost_usd=cost,
        duration_ms=duration_ms,
        num_turns=num_turns,
        timestamp=timestamp,
    )


def generate_workflow(
    start_date: datetime,
    end_date: datetime,
) -> tuple[WorkflowData, list[TokenUsage]]:
    """Generate a workflow with associated token usage."""
    workflow_id = str(uuid4())
    issue_id = random_issue_id()
    worktree_path = f"/tmp/worktrees/{workflow_id[:8]}"

    # Random timestamp within range
    time_range = (end_date - start_date).total_seconds()
    random_offset = random.uniform(0, time_range)
    created_at = start_date + timedelta(seconds=random_offset)

    status = weighted_choice(WORKFLOW_STATUSES)

    # Set timestamps based on status
    started_at = None
    completed_at = None
    failure_reason = None

    if status != "pending":
        started_at = created_at + timedelta(seconds=random.randint(1, 60))

    if status == "completed":
        assert started_at is not None  # Set above for non-pending statuses
        completed_at = started_at + timedelta(seconds=random.randint(300, 3600))
    elif status == "failed":
        assert started_at is not None
        completed_at = started_at + timedelta(seconds=random.randint(60, 600))
        failure_reason = random.choice([
            "LLM API error: rate limit exceeded",
            "Git conflict during merge",
            "Tests failed after 3 attempts",
            "Reviewer rejected changes: security concern",
            "Timeout waiting for developer response",
        ])
    elif status == "cancelled":
        assert started_at is not None
        completed_at = started_at + timedelta(seconds=random.randint(60, 300))

    state = WorkflowData(
        id=workflow_id,
        issue_id=issue_id,
        worktree_path=worktree_path,
        workflow_status=status,
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        failure_reason=failure_reason,
    )

    # Generate token usage based on workflow status
    token_usages: list[TokenUsage] = []
    model = weighted_choice(MODELS)

    # Generate token usage for non-pending workflows (started_at is set)
    if status != "pending" and started_at is not None:
        if status == "cancelled":
            # Only architect ran
            token_usages.append(
                generate_token_usage(workflow_id, "architect", started_at, model)
            )
        elif status == "failed":
            # Architect and maybe developer ran
            token_usages.append(
                generate_token_usage(workflow_id, "architect", started_at, model)
            )
            if random.random() > 0.3:
                dev_time = started_at + timedelta(seconds=random.randint(60, 300))
                token_usages.append(
                    generate_token_usage(workflow_id, "developer", dev_time, model)
                )
        elif status in ("in_progress", "blocked"):
            # Architect done, developer may be running
            token_usages.append(
                generate_token_usage(workflow_id, "architect", started_at, model)
            )
            if random.random() > 0.4:
                dev_time = started_at + timedelta(seconds=random.randint(60, 300))
                token_usages.append(
                    generate_token_usage(workflow_id, "developer", dev_time, model)
                )
        else:  # completed
            # All agents ran, possibly multiple dev/review cycles
            arch_time = started_at
            token_usages.append(
                generate_token_usage(workflow_id, "architect", arch_time, model)
            )

            dev_time = arch_time + timedelta(seconds=random.randint(120, 600))
            token_usages.append(
                generate_token_usage(workflow_id, "developer", dev_time, model)
            )

            # Number of review cycles (1-3)
            review_cycles = random.randint(1, 3)
            for i in range(review_cycles):
                review_time = dev_time + timedelta(
                    seconds=random.randint(60, 300) * (i + 1)
                )
                token_usages.append(
                    generate_token_usage(workflow_id, "reviewer", review_time, model)
                )
                if i < review_cycles - 1:
                    # Developer responded to review
                    dev_response_time = review_time + timedelta(
                        seconds=random.randint(120, 600)
                    )
                    token_usages.append(
                        generate_token_usage(
                            workflow_id, "developer", dev_response_time, model
                        )
                    )

    return state, token_usages


async def populate_data(days: int, num_workflows: int, db_path: str) -> None:
    """Populate the database with test data."""
    print(f"Populating database at: {db_path}")
    print(f"Generating {num_workflows} workflows over {days} days")

    db = Database(Path(db_path))
    async with db:
        # Ensure schema exists
        await db.ensure_schema()

        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=days)

        total_cost = 0.0
        total_tokens = 0

        for i in range(num_workflows):
            state, token_usages = generate_workflow(start_date, end_date)

            # Create minimal state_json (just enough for the database)
            state_json = json.dumps({
                "id": state.id,
                "issue_id": state.issue_id,
                "worktree_path": state.worktree_path,
                "workflow_status": state.workflow_status,
                "created_at": state.created_at.isoformat() if state.created_at else None,
                "started_at": state.started_at.isoformat() if state.started_at else None,
                "completed_at": state.completed_at.isoformat() if state.completed_at else None,
                "failure_reason": state.failure_reason,
            })

            # Insert workflow
            await db.execute(
                """
                INSERT INTO workflows (
                    id, issue_id, worktree_path,
                    status, created_at, started_at, completed_at, failure_reason, state_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.id,
                    state.issue_id,
                    state.worktree_path,
                    state.workflow_status,
                    state.created_at.isoformat() if state.created_at else None,
                    state.started_at.isoformat() if state.started_at else None,
                    state.completed_at.isoformat() if state.completed_at else None,
                    state.failure_reason,
                    state_json,
                ),
            )

            # Insert token usage
            for usage in token_usages:
                await db.execute(
                    """
                    INSERT INTO token_usage (
                        id, workflow_id, agent, model, input_tokens, output_tokens,
                        cache_read_tokens, cache_creation_tokens, cost_usd,
                        duration_ms, num_turns, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        usage.id,
                        usage.workflow_id,
                        usage.agent,
                        usage.model,
                        usage.input_tokens,
                        usage.output_tokens,
                        usage.cache_read_tokens,
                        usage.cache_creation_tokens,
                        usage.cost_usd,
                        usage.duration_ms,
                        usage.num_turns,
                        usage.timestamp.isoformat(),
                    ),
                )
                total_cost += usage.cost_usd
                total_tokens += usage.input_tokens + usage.output_tokens

            if (i + 1) % 10 == 0:
                print(f"  Created {i + 1}/{num_workflows} workflows...")

    print("\nDone!")
    print(f"  Total workflows: {num_workflows}")
    print(f"  Total cost: ${total_cost:.2f}")
    print(f"  Total tokens: {total_tokens:,}")
    print("\nTo view the data, start the server:")
    print("  uv run amelia dev")
    print("\nThen open: http://localhost:8420/costs")
    print("\nTo clean up, delete the database:")
    print(f"  rm {db_path}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Populate the database with test data for UI development.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    uv run scripts/populate_test_data.py                    # Default: 365 days, 200 workflows
    uv run scripts/populate_test_data.py --days 30          # Last 30 days
    uv run scripts/populate_test_data.py --workflows 500    # 500 workflows
    uv run scripts/populate_test_data.py --db /tmp/test.db  # Custom database path

To clean up test data, simply delete the database file.
        """,
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Number of days to spread data over (default: 365)",
    )
    parser.add_argument(
        "--workflows",
        type=int,
        default=200,
        help="Number of workflows to generate (default: 200)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Database path (default: ~/.amelia/amelia.db)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible data",
    )

    args = parser.parse_args()

    if args.days <= 0:
        parser.error("--days must be >= 1")
    if args.workflows <= 0:
        parser.error("--workflows must be >= 1")

    if args.seed is not None:
        random.seed(args.seed)

    db_path = args.db or str(ServerConfig().database_path)

    asyncio.run(populate_data(args.days, args.workflows, db_path))


if __name__ == "__main__":
    main()
