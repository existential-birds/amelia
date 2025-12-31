from pathlib import Path

from amelia.core.types import Design
from amelia.drivers.base import DriverInterface


PARSER_SYSTEM_PROMPT = """You are a design document parser. Extract structured information from the given markdown design document.

Parse the document and return a Design object with these fields:
- title: The main title/feature name
- goal: A one-sentence description of what this builds
- architecture: 2-3 sentences about the approach
- tech_stack: List of key technologies/libraries mentioned
- components: List of major components to build
- data_flow: How data moves through the system (if mentioned)
- error_handling: Error handling approach (if mentioned)
- testing_strategy: Testing approach (if mentioned)
- relevant_files: Existing files mentioned that need modification
- conventions: Code style or conventions mentioned

Extract only what is explicitly stated or clearly implied. Use null for fields not covered in the document."""


async def parse_design(path: str | Path, driver: DriverInterface) -> Design:
    """Parse a brainstorming markdown file into structured Design object.

    Uses the LLM driver to extract structured fields from freeform markdown
    design documents. The raw markdown content is preserved in the Design object.

    Args:
        path: Path to the markdown design document.
        driver: LLM driver interface for structured extraction.

    Returns:
        Design object with extracted structured fields and raw content.

    Raises:
        FileNotFoundError: If the design file does not exist at the specified path.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Design file not found: {path}")

    content = path.read_text()

    parsed_result, _session_id = await driver.generate(
        prompt=content,
        system_prompt=PARSER_SYSTEM_PROMPT,
        schema=Design
    )
    design: Design = parsed_result  # Type assertion - schema was provided
    design.raw_content = content
    return design
