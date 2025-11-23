import pytest
from amelia.drivers.api.openai import ApiDriver

@pytest.mark.asyncio
async def test_api_driver_write_file(tmp_path):
    driver = ApiDriver()
    test_file = tmp_path / "test.txt"
    await driver.execute_tool("write_file", file_path=str(test_file), content="Hello World")
    assert test_file.read_text() == "Hello World"

@pytest.mark.asyncio
async def test_api_driver_shell_command():
    driver = ApiDriver()
    result = await driver.execute_tool("run_shell_command", command="echo 'test'")
    assert "test" in result.strip()
