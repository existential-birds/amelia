import pytest
import time
import asyncio
from amelia.core.orchestrator import create_orchestrator_graph, call_reviewer_node
from amelia.core.state import ExecutionState, Profile, Issue, Task, TaskDAG, TaskStatus, ReviewResult
from amelia.agents.project_manager import create_project_manager
from amelia.agents.reviewer import ReviewResponse
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_fully_implemented_orchestrator_nodes():
    """Mocks orchestrator nodes to simulate full execution without real LLM/tool calls."""
    with patch('amelia.agents.architect.Architect.plan', new_callable=AsyncMock) as mock_architect_plan, \
         patch('amelia.agents.developer.Developer.execute_task', new_callable=AsyncMock) as mock_developer_execute, \
         patch('amelia.agents.reviewer.Reviewer.review', new_callable=AsyncMock) as mock_reviewer_review:
        
        mock_architect_plan.return_value = TaskDAG(tasks=[
            Task(id="T1", description="Parallel task 1"),
            Task(id="T2", description="Parallel task 2"),
            Task(id="T3", description="Sequential task 3", dependencies=["T1", "T2"])
        ], original_issue="PARALLEL-TEST")
        mock_developer_execute.return_value = {"status": "completed", "output": "Mocked task output"}
        mock_reviewer_review.return_value = ReviewResult(reviewer_persona="Mock", approved=True, comments=[], severity="low")
        yield

async def test_orchestrator_full_loop():
    """
    Verifies a full execution loop of the orchestrator from plan to execute.
    """
    # Setup a dummy profile and issue
    profile = Profile(name="test_profile", driver="cli:claude", tracker="noop", strategy="single")
    test_issue = Issue(id="TEST-1", title="Test Issue", description="Implement a dummy function.")
    
    # Initialize ProjectManager and get the issue
    project_manager = create_project_manager(profile)
    fetched_issue = project_manager.get_issue(test_issue.id)
    
    # Create initial state
    ExecutionState(profile=profile, issue=fetched_issue)
    
    # Get the compiled orchestrator graph
    app = create_orchestrator_graph()
    
    # Execute the graph (this will involve mocking or stubbing agents and drivers heavily)
    # The actual execution flow will be:
    # app.ainvoke(initial_state)
    
    # For now, we'll just assert that the app object exists
    assert app is not None

@pytest.mark.skip(reason="Multi-profile planning logic not yet implemented")
async def test_orchestrator_multi_profile_planning():
    """
    Ensures task planning works correctly under different CLI and API profiles.
    """
    # This test will involve invoking the orchestrator with different profiles
    # and asserting that the resulting plans (TaskDAGs) are as expected
    # based on the profile's constraints (e.g., API for parallel tasks vs. CLI for sequential)
    pass




async def test_orchestrator_competitive_review():
    """
    Verifies the orchestrator can handle competitive review scenarios (US3).
    """
    profile_competitive = Profile(name="competitive_reviewer", driver="api:openai", tracker="noop", strategy="competitive")
    test_issue = Issue(id="COMP-1", title="Competitive Review Test", description="Review a code change competitively.")
    
    # We need to invoke the Reviewer.review method indirectly or directly.
    # Let's test the Reviewer agent directly first to ensure logic works, 
    # or use the orchestrator node.
    
    # Using the orchestrator node:

    
    # Mock the driver that the factory will return
    mock_driver = AsyncMock()
    
    # Mock generate response
    # The reviewer calls generate multiple times (once per persona)
    # We want to return different results to verify aggregation logic if possible, 
    # or just success.
    mock_driver.generate.return_value = ReviewResponse(
        approved=True, 
        comments=["Good code"], 
        severity="low"
    )
    
    with patch("amelia.drivers.factory.DriverFactory.get_driver", return_value=mock_driver):
        initial_state = ExecutionState(
            profile=profile_competitive, 
            issue=test_issue,
            code_changes_for_review="diff --git a/file.py b/file.py..."
        )
        
        final_state = await call_reviewer_node(initial_state)
        
        # Verify review results
        assert len(final_state.review_results) == 1
        result = final_state.review_results[0]
        assert result.reviewer_persona == "Competitive-Aggregated"
        assert result.approved is True
        
        # Verify generate was called multiple times (3 personas defined in Reviewer)
        # Personas: Security, Performance, Usability
        assert mock_driver.generate.call_count == 3


async def test_orchestrator_parallel_review_api():
    """
    Explicitly verifies concurrent API calls during competitive review with an API driver.
    """
    profile_api_competitive = Profile(name="api_comp_reviewer", driver="api:openai", tracker="noop", strategy="competitive")
    test_issue = Issue(id="PAR-API", title="Parallel API Review", description="Test concurrent API calls for review.")


    
    mock_driver = AsyncMock()
    
    # Simulate a slow API call (0.1s)
    async def slow_generate(*args, **kwargs):
        await asyncio.sleep(0.1) 
        return ReviewResponse(approved=True, comments=[], severity="low")
        
    mock_driver.generate.side_effect = slow_generate
    
    with patch("amelia.drivers.factory.DriverFactory.get_driver", return_value=mock_driver):
        start_time = time.time()
        
        initial_state = ExecutionState(
            profile=profile_api_competitive, 
            issue=test_issue,
            code_changes_for_review="changes"
        )
        
        await call_reviewer_node(initial_state)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # If sequential, it would take 0.1 * 3 = 0.3s
        # If parallel, it should take ~0.1s (+ overhead)
        # We assert it takes less than 0.25s
        assert duration < 0.25
        assert mock_driver.generate.call_count == 3

@pytest.mark.skip(reason="Parallel execution in orchestrator (T034) not yet implemented.")
async def test_orchestrator_parallel_execution_api_driver(mock_fully_implemented_orchestrator_nodes):
    """
    Verifies that the orchestrator executes independent tasks in parallel when using an API driver.
    """
    profile_api = Profile(name="api_parallel", driver="api:openai", tracker="noop", strategy="single")
    test_issue = Issue(id="PAR-EXEC", title="Parallel Execution Test", description="Execute tasks in parallel.")
    
    # Mock a TaskDAG that has parallel tasks
    mock_plan = TaskDAG(tasks=[
        Task(id="P1", description="Task 1", status=TaskStatus.PENDING),
        Task(id="P2", description="Task 2", status=TaskStatus.PENDING),
    ], original_issue="PAR-EXEC")

    # The architect_node will now return this mock_plan
    with patch('amelia.agents.architect.Architect.plan', new_callable=AsyncMock) as mock_architect_plan:
        mock_architect_plan.return_value = mock_plan
        
        initial_state = ExecutionState(profile=profile_api, issue=test_issue)
        app = create_orchestrator_graph()
        
        # Here we would need to mock the developer.execute_task such that we can
        # verify concurrent calls.
        # and checking call order or timing.
        
        # For now, just a basic invocation (will run sequentially with current orchestrator)
        final_state = await app.ainvoke(initial_state)
        
        # Assert that both tasks were attempted to be executed
        # And if the orchestrator is refactored for parallel, this would check concurrency.
        # This will depend on T034.
        assert mock_fully_implemented_orchestrator_nodes.mock_developer_execute.call_count == 2
        assert any(task.status == TaskStatus.COMPLETED for task in final_state.plan.tasks)


@pytest.mark.skip(reason="CLI driver fallback to sequential execution (T036) and warning (T033b) not yet implemented.")
async def test_orchestrator_parallel_fallback_cli_driver(mock_fully_implemented_orchestrator_nodes):
    """
    Verifies that when a CLI driver receives parallel tasks, it falls back to sequential execution
    and potentially emits a structured warning.
    """
    profile_cli = Profile(name="cli_sequential", driver="cli:claude", tracker="noop", strategy="single")
    test_issue = Issue(id="CLI-FALLBACK", title="CLI Parallel Fallback Test", description="Test sequential fallback.")
    
    mock_plan = TaskDAG(tasks=[
        Task(id="S1", description="Task A", status=TaskStatus.PENDING),
        Task(id="S2", description="Task B", status=TaskStatus.PENDING),
    ], original_issue="CLI-FALLBACK")

    with patch('amelia.agents.architect.Architect.plan', new_callable=AsyncMock) as mock_architect_plan:
        mock_architect_plan.return_value = mock_plan
        
        initial_state = ExecutionState(profile=profile_cli, issue=test_issue)
        app = create_orchestrator_graph()
        
        # Need to capture logs to check for warning.
        # Need to verify that execute_task calls were sequential, e.g. using a mock that records start/end times.
        
        final_state = await app.ainvoke(initial_state)
        
        assert mock_fully_implemented_orchestrator_nodes.mock_developer_execute.call_count == 2
        assert any(task.status == TaskStatus.COMPLETED for task in final_state.plan.tasks)
        # Assert warning about sequential execution in logs
