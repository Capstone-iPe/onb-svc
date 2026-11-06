import asyncio

from onb.server import mcp

EXPECTED = {"next_step", "save_answer", "save_file", "submit", "get_review"}


def test_advertises_the_five_tools() -> None:
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == EXPECTED


def test_the_tool_descriptions_name_the_answer_formats() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}

    assert "₹12,00,000" in tools["next_step"].description
    assert "yes or no" in tools["next_step"].description
    assert "PDF, JPG, or PNG" in tools["next_step"].description

    save_answer = tools["save_answer"]
    assert "₹12,00,000" in save_answer.description
    assert "yes or no" in save_answer.description
    assert "₹12,00,000" in save_answer.input_schema["properties"]["value"]["description"]
    assert "yes or no" in save_answer.input_schema["properties"]["value"]["description"]

    save_file = tools["save_file"]
    assert "PDF, JPG, or PNG" in save_file.description
    assert "PDF, JPG, or PNG" in save_file.input_schema["properties"]["file"]["description"]
