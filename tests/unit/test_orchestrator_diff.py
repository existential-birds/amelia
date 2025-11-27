from unittest.mock import patch

import pytest

from amelia.core.orchestrator import get_code_changes_for_review
from amelia.core.state import ExecutionState


@pytest.mark.asyncio
async def test_get_real_git_diff():
    from amelia.core.types import Issue
    from amelia.core.types import Profile
    
    # Setup valid Profile and Issue
    profile = Profile(name="test", driver="cli", tracker="none", strategy="single")
    issue = Issue(id="TEST-1", title="Test", description="Test desc", status="open")
    
    state = ExecutionState(
        profile=profile,
        issue=issue,
        plan=None,
        code_changes_for_review=None 
    )
    
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "diff --git a/file b/file..."
        mock_run.return_value.returncode = 0
        
        diff = await get_code_changes_for_review(state)
        
        assert "diff --git" in diff
        mock_run.assert_called_with(["git", "diff", "HEAD"], capture_output=True, text=True, check=False)
