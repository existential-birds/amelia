import asyncio
from typing import Any

import typer
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END
from langgraph.graph import StateGraph
from loguru import logger

from amelia.agents.architect import Architect
from amelia.agents.developer import Developer
from amelia.agents.reviewer import Reviewer
from amelia.core.state import AgentMessage
from amelia.core.state import ExecutionState
from amelia.core.state import TaskDAG
from amelia.drivers.factory import DriverFactory


# Define nodes for the graph
async def call_architect_node(state: ExecutionState) -> ExecutionState:
    """
    Orchestrator node for the Architect agent to generate a plan.
    """
    issue_id_for_log = state.issue.id if state.issue else "No Issue Provided"
    logger.info(f"Orchestrator: Calling Architect for issue {issue_id_for_log}")
    
    if state.issue is None:
        raise ValueError("Cannot call Architect: no issue provided in state.")
        
    driver = DriverFactory.get_driver(state.profile.driver)
    architect = Architect(driver)
    plan_output = await architect.plan(state.issue, output_dir=state.profile.plan_output_dir)

    # Add a message to the state history
    messages = state.messages + [AgentMessage(role="assistant", content=f"Architect generated plan with {len(plan_output.task_dag.tasks)} tasks.")]

    # Return the updated state
    return ExecutionState(
        profile=state.profile,
        issue=state.issue,
        plan=plan_output.task_dag,
        messages=messages
    )

async def human_approval_node(state: ExecutionState) -> ExecutionState:
    """
    Node to prompt for human approval before proceeding.
    """
    typer.secho("\n--- HUMAN APPROVAL REQUIRED ---", fg=typer.colors.BRIGHT_YELLOW)
    typer.echo("Review the proposed plan before proceeding. State snapshot (for debug):")
    typer.echo(f"Plan for issue {state.issue.id if state.issue else 'N/A'}:")
    if state.plan:
        for task in state.plan.tasks:
            typer.echo(f"  - [{task.id}] {task.description} (Dependencies: {', '.join(task.dependencies)})")
    
    approved = typer.confirm("Do you approve this plan to proceed with development?", default=True)
    comment = typer.prompt("Add an optional comment for the audit log (press Enter to skip)", default="")

    approval_message = f"Human approval: {'Approved' if approved else 'Rejected'}. Comment: {comment}"
    messages = state.messages + [AgentMessage(role="system", content=approval_message)]
    
    return ExecutionState(
        profile=state.profile,
        issue=state.issue,
        plan=state.plan,
        messages=messages,
        human_approved=approved
    )

async def get_code_changes_for_review(state: ExecutionState) -> str:
    """
    Retrieves code changes for review. Prioritizes changes from state,
    otherwise attempts to get git diff.
    """
    if state.code_changes_for_review:
        return state.code_changes_for_review
    
    import subprocess
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            return result.stdout
        else:
            return f"Error getting git diff: {result.stderr}"
    except Exception as e:
        return f"Failed to execute git diff: {str(e)}"

async def call_reviewer_node(state: ExecutionState) -> ExecutionState:
    """
    Orchestrator node for the Reviewer agent to review code changes.
    """
    logger.info(f"Orchestrator: Calling Reviewer for issue {state.issue.id if state.issue else 'N/A'}")
    driver = DriverFactory.get_driver(state.profile.driver)
    reviewer = Reviewer(driver)

    code_changes = await get_code_changes_for_review(state)
    review_result = await reviewer.review(state, code_changes)

    review_msg = f"Reviewer completed review: {review_result.severity}, Approved: {review_result.approved}."
    logger.info(review_msg)
    messages = state.messages + [AgentMessage(role="assistant", content=review_msg)]
    
    # Update state with review results
    review_results = state.review_results + [review_result]

    return ExecutionState(
        profile=state.profile,
        issue=state.issue,
        plan=state.plan,
        messages=messages,
        human_approved=state.human_approved,
        review_results=review_results
    )

async def call_developer_node(state: ExecutionState) -> ExecutionState:
    """
    Orchestrator node for the Developer agent to execute tasks, potentially in parallel.
    """
    logger.info("Orchestrator: Calling Developer to execute tasks.")

    if not state.plan or not state.plan.tasks:
        logger.info("Orchestrator: No plan or tasks to execute.")
        return state
    
    driver = DriverFactory.get_driver(state.profile.driver)
    developer = Developer(driver)
    
    ready_tasks = state.plan.get_ready_tasks()
    
    if not ready_tasks:
        logger.info("Orchestrator: No ready tasks found to execute in this iteration.")
        return state  # No tasks to run in this step

    logger.info(f"Orchestrator: Executing {len(ready_tasks)} ready tasks.")
    
    # Mark tasks as in-progress before execution
    for task in ready_tasks:
        task.status = "in_progress"
        logger.info(f"Orchestrator: Developer executing task {task.id}")
    
    # Execute tasks concurrently if driver supports it, otherwise sequentially
    # This logic assumes the driver's generate/execute_tool handles concurrency,
    # or that asyncio.gather provides the concurrency when the driver is async.
    task_execution_futures = [developer.execute_task(task) for task in ready_tasks]
    results = await asyncio.gather(*task_execution_futures, return_exceptions=True) # Gather results, including exceptions
    
    updated_messages = list(state.messages)
    # The tasks in state.plan.tasks list are modified directly in the loop.
    
    for i, result in enumerate(results):
        executed_task = ready_tasks[i]
        if isinstance(result, Exception):
            executed_task.status = "failed"
            updated_messages.append(AgentMessage(role="assistant", content=f"Task {executed_task.id} failed. Error: {result}"))
        else:
            executed_task.status = "completed"
            output_content = result.get('output', 'No output') if isinstance(result, dict) else str(result)
            updated_messages.append(AgentMessage(role="assistant", content=f"Task {executed_task.id} completed. Output: {output_content}"))
            
    # Update the overall plan in the state to reflect completed/failed tasks
    updated_plan = TaskDAG(tasks=state.plan.tasks, original_issue=state.plan.original_issue)
            
    return ExecutionState(
        profile=state.profile,
        issue=state.issue,
        plan=updated_plan,
        current_task_id=ready_tasks[0].id if ready_tasks else state.current_task_id, # Can be multiple, pick one for current_task_id or make it a list
        messages=updated_messages,
        human_approved=state.human_approved,
        review_results=state.review_results
    )

# Define a conditional edge to decide if more tasks need to be run
def should_continue_developer(state: ExecutionState) -> str:
    """Determine whether to continue the developer loop.
    
    Returns 'continue' if there are ready tasks to execute.
    Returns 'end' if:
    - No plan exists
    - All tasks are completed
    - Pending tasks exist but none are ready (blocked by failed dependencies)
    """
    if not state.plan:
        return "end"
    
    # Check for ready tasks, not just pending tasks.
    # This prevents infinite loops when tasks are blocked by failed dependencies.
    ready_tasks = state.plan.get_ready_tasks()
    if ready_tasks:
        return "continue"
    return "end"

def should_continue_review_loop(state: ExecutionState) -> str:
    """Determine whether to continue the review loop.

    Returns 're_evaluate' if review was not approved AND there are tasks to execute.
    Returns 'end' if:
    - Review was approved
    - Review was not approved but no tasks are ready (workflow is stuck)
    """
    if state.review_results and not state.review_results[-1].approved:
        # Only re-evaluate if there are tasks that can be executed
        if state.plan and state.plan.get_ready_tasks():
            return "re_evaluate"
        # No tasks available - log and exit to prevent infinite loop
        logger.warning(
            "Review not approved but no tasks available to execute. "
            "Ending workflow - manual intervention may be required."
        )
        return "end"
    return "end"

def create_orchestrator_graph(checkpoint_saver: MemorySaver | None = None) -> Any:
    """
    Creates and compiles the LangGraph state machine for the orchestrator.
    Configures checkpointing if a saver is provided.
    """
    workflow = StateGraph(ExecutionState)
    
    # Add nodes
    workflow.add_node("architect_node", call_architect_node)
    workflow.add_node("human_approval_node", human_approval_node)
    workflow.add_node("developer_node", call_developer_node)
    workflow.add_node("reviewer_node", call_reviewer_node)
    
    # Set entry point
    workflow.set_entry_point("architect_node")
    
    # Define edges
    workflow.add_edge("architect_node", "human_approval_node")
    
    # Conditional edge from human_approval_node: if approved, go to developer_node, else END
    workflow.add_conditional_edges(
        "human_approval_node",
        lambda state: "approve" if state.human_approved else "reject",
        {
            "approve": "developer_node",
            "reject": END
        }
    )
    
    # Developer -> Reviewer (after all development tasks are done)
    workflow.add_conditional_edges(
        "developer_node",
        should_continue_developer,
        {
            "continue": "developer_node",
            "end": "reviewer_node"
        }
    )
    
    # Reviewer -> Developer (if not approved) or END (if approved)
    workflow.add_conditional_edges(
        "reviewer_node",
        should_continue_review_loop,
        {
            "re_evaluate": "developer_node",
            "end": END
        }
    )
    
    app = workflow.compile()
    
    if checkpoint_saver:
        app = app.with_config({"configurable": {"checkpoint_saver": checkpoint_saver}})
        
    return app
