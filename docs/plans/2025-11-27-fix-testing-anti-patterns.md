# Fix Testing Anti-Patterns Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove assertions that test mock passthrough behavior (asserting return value equals mocked value) from unit tests.

**Architecture:** Each task removes redundant assertions from test files. The meaningful assertions (call verification, call count, argument verification) remain. Tasks are independent and can be executed in parallel.

**Tech Stack:** Python, pytest, unittest.mock

---

## Summary of Anti-Pattern

Tests that do this are testing mock behavior, not real behavior:
```python
mock.return_value = "X"
result = code_under_test()
assert result == "X"  # ANTI-PATTERN: Just tests the mock works
```

The fix: Remove the `assert result == "X"` line. Keep assertions that verify the mock was called correctly.

---

### Task 1: Fix test_developer_real.py

**Files:**
- Modify: `tests/unit/test_developer_real.py:31`

**Step 1: Remove the mock passthrough assertion**

The test currently has:
```python
mock_driver.execute_tool.assert_called_once()
assert result["output"] == "File created"  # REMOVE THIS LINE
```

Change to:
```python
mock_driver.execute_tool.assert_called_once()
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_developer_real.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/unit/test_developer_real.py
git commit -m "fix(tests): remove mock passthrough assertion in test_developer_real"
```

---

### Task 2: Fix test_cli_timeout.py - timeout retry test

**Files:**
- Modify: `tests/unit/test_cli_timeout.py:34`

**Step 1: Remove the mock passthrough assertion**

In `test_cli_driver_execute_tool_timeout_retry`, the test currently has:
```python
result = await driver.execute_tool("run_shell_command", command="echo test")

assert result == "Success Output"  # REMOVE THIS LINE
assert mock_run.call_count == 2
```

Change to:
```python
result = await driver.execute_tool("run_shell_command", command="echo test")

# Verify retry happened (2 calls = initial + 1 retry)
assert mock_run.call_count == 2
```

Note: Keep `result = await ...` as it's needed to trigger the behavior.

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli_timeout.py::test_cli_driver_execute_tool_timeout_retry -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/unit/test_cli_timeout.py
git commit -m "fix(tests): remove mock passthrough assertion in timeout retry test"
```

---

### Task 3: Fix test_cli_timeout.py - generate retry test

**Files:**
- Modify: `tests/unit/test_cli_timeout.py:66`

**Step 1: Remove the mock passthrough assertion**

In `test_cli_driver_generate_retry`, the test currently has:
```python
result = await driver.generate([AgentMessage(role="user", content="hi")])

assert result == "Generated Content"  # REMOVE THIS LINE
assert driver._generate_impl.call_count == 2
```

Change to:
```python
result = await driver.generate([AgentMessage(role="user", content="hi")])

# Verify retry happened (2 calls = initial + 1 retry)
assert driver._generate_impl.call_count == 2
```

Note: Keep `result = await ...` as it's needed to trigger the behavior.

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli_timeout.py::test_cli_driver_generate_retry -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/unit/test_cli_timeout.py
git commit -m "fix(tests): remove mock passthrough assertion in generate retry test"
```

---

### Task 4: Fix test_claude_driver.py - shell command test

**Files:**
- Modify: `tests/unit/test_claude_driver.py:137`

**Step 1: Remove the mock passthrough assertion**

In `test_execute_tool_shell`, the test currently has:
```python
mock_run.return_value = "Output"
result = await driver._execute_tool_impl("run_shell_command", command="echo test")
assert result == "Output"  # REMOVE THIS LINE
mock_run.assert_called_once_with("echo test", timeout=driver.timeout)
```

Change to:
```python
mock_run.return_value = "Output"
await driver._execute_tool_impl("run_shell_command", command="echo test")
mock_run.assert_called_once_with("echo test", timeout=driver.timeout)
```

Note: Remove the `result =` assignment since we no longer use `result`.

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeCliDriver::test_execute_tool_shell -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/unit/test_claude_driver.py
git commit -m "fix(tests): remove mock passthrough assertion in test_execute_tool_shell"
```

---

### Task 5: Fix test_claude_driver.py - write file test

**Files:**
- Modify: `tests/unit/test_claude_driver.py:144-145`

**Step 1: Remove the mock passthrough assertion**

In `test_execute_tool_write_file`, the test currently has:
```python
mock_write.return_value = "Success"
result = await driver._execute_tool_impl("write_file", file_path="test.txt", content="data")
assert result == "Success"  # REMOVE THIS LINE
mock_write.assert_called_once_with("test.txt", "data")
```

Change to:
```python
mock_write.return_value = "Success"
await driver._execute_tool_impl("write_file", file_path="test.txt", content="data")
mock_write.assert_called_once_with("test.txt", "data")
```

Note: Remove the `result =` assignment since we no longer use `result`.

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeCliDriver::test_execute_tool_write_file -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/unit/test_claude_driver.py
git commit -m "fix(tests): remove mock passthrough assertion in test_execute_tool_write_file"
```

---

### Task 6: Final verification

**Step 1: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All tests PASS

**Step 2: Run linting**

Run: `uv run ruff check tests/unit/`
Expected: No errors

**Step 3: Run type checking**

Run: `uv run mypy amelia`
Expected: No errors

**Step 4: Final commit (if any lint fixes needed)**

```bash
git add -A
git commit -m "chore: lint fixes after test cleanup"
```

---

## Parallel Execution Note

Tasks 1-5 are **independent** and can be executed by parallel subagents:
- Task 1: `test_developer_real.py`
- Task 2: `test_cli_timeout.py` (timeout retry)
- Task 3: `test_cli_timeout.py` (generate retry)
- Task 4: `test_claude_driver.py` (shell)
- Task 5: `test_claude_driver.py` (write file)

Task 6 must run **after** all others complete.
