import asyncio

from onb.server import mcp

EXPECTED = {"next_step", "save_answer", "save_file", "submit", "get_review"}


def test_advertises_the_five_tools() -> None:
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == EXPECTED
