"""Oracle consultation tool for agents.

Provides expert guidance when agents are stuck by bundling
file context and querying an LLM for consultation.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Any, Optional

from amelia.core.oracle_types import OracleConsultation, OracleEventType
from amelia.tools.file_bundler import bundle_files


async def oracle_consult(
    question: str,
    file_patterns: list[str],
    execution_state: Any,
    llm_client: Any,
) -> dict[str, Any]:
    """Consult the Oracle with bundled file context.

    Args:
        question: The question to ask Oracle
        file_patterns: Glob patterns for files to bundle
        execution_state: Current execution state
        llm_client: LLM client for consultation

    Returns:
        Consultation result with guidance
    """
    consultation_id = str(uuid.uuid4())
    start_time = datetime.now()

    try:
        consultation = OracleConsultation(
            request_id=consultation_id,
            requested_at=start_time,
            status="bundling",
            file_patterns=file_patterns,
        )
        execution_state.oracle_consultations.append(consultation)

        # Bundle files
        bundled_content, token_count = await bundle_files(
            root_dir=".",
            patterns=file_patterns,
            max_tokens=execution_state.profile.oracle.max_bundle_tokens,
        )

        consultation.bundled_content = bundled_content
        consultation.bundled_tokens = token_count
        consultation.status = "consulting"

        # Query LLM
        prompt = f"""You are an expert consultant helping a developer.
Based on the provided context, answer this question:

Question: {question}

Context:
{bundled_content}

Provide practical guidance and recommendations."""

        response = await llm_client.agenerate_text(prompt)

        consultation.llm_response = response
        consultation.status = "completed"
        consultation.duration_ms = (
            (datetime.now() - start_time).total_seconds() * 1000
        )

        return {
            "success": True,
            "consultation_id": consultation_id,
            "response": response,
            "tokens_used": token_count,
            "duration_ms": consultation.duration_ms,
        }

    except Exception as e:
        consultation.status = "completed"
        consultation.error = str(e)
        consultation.duration_ms = (
            (datetime.now() - start_time).total_seconds() * 1000
        )
        return {
            "success": False,
            "consultation_id": consultation_id,
            "error": str(e),
        }
