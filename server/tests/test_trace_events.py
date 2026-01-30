import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import agno_api  # noqa: E402
from agno.run.agent import RunEvent  # noqa: E402
from agno.run.team import TeamRunEvent  # noqa: E402


def test_map_reasoning_step_event():
    event = SimpleNamespace(
        event=TeamRunEvent.reasoning_step.value,
        reasoning_content="步驟一：確認文件",
        run_id="run-1",
        session_id="sess-1",
        agent_name="Team",
        created_at=123,
    )
    trace = agno_api.map_event_to_trace_event(event)
    assert trace["type"] == "reasoning_step"
    assert trace["data"]["text"] == "步驟一：確認文件"
    assert trace["run_id"] == "run-1"


def test_map_tool_events():
    tool = SimpleNamespace(
        tool_name="web_search",
        tool_args={"query": "台積電 最新新聞"},
        result={"title": "示例新聞"},
        tool_call_id="tool-1",
    )
    start_event = SimpleNamespace(
        event=TeamRunEvent.tool_call_started.value,
        tool=tool,
        run_id="run-2",
    )
    done_event = SimpleNamespace(
        event=TeamRunEvent.tool_call_completed.value,
        tool=tool,
        run_id="run-2",
    )
    start_trace = agno_api.map_event_to_trace_event(start_event)
    done_trace = agno_api.map_event_to_trace_event(done_event)
    assert start_trace["type"] == "tool_start"
    assert "台積電" in start_trace["data"]["args"]
    assert done_trace["type"] == "tool_done"
    assert "示例新聞" in done_trace["data"]["result"]


def test_map_content_filters_json():
    event = SimpleNamespace(
        event=TeamRunEvent.run_content.value,
        content='{"assistant": "ok"}',
        run_id="run-3",
    )
    trace = agno_api.map_event_to_trace_event(event)
    assert trace is None


def test_map_content_plain_text():
    event = SimpleNamespace(
        event=TeamRunEvent.run_content.value,
        content="正在查詢資料中...",
        run_id="run-4",
    )
    trace = agno_api.map_event_to_trace_event(event)
    assert trace["type"] == "content"
    assert "查詢" in trace["data"]["text"]


@pytest.mark.integration
def test_live_stream_events():
    if not os.getenv("RUN_LIVE_AGNO_TESTS"):
        pytest.skip("Set RUN_LIVE_AGNO_TESTS=1 to enable live OpenAI streaming test.")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set.")

    from agno.team import Team
    from agno.models.openai.responses import OpenAIResponses

    model_id = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    model = OpenAIResponses(id=model_id, api_key=api_key)

    team = Team(
        name="TraceTest",
        members=[],
        model=model,
        tools=[agno_api.WEB_SEARCH_TOOL],
        instructions=[
            "你是測試代理，必須先使用 web_search 後再回覆。",
        ],
        markdown=False,
    )
    team.tool_choice = agno_api.WEB_SEARCH_TOOL

    response = team.run(
        "請使用 web_search 查詢台灣最新新聞，列出一則標題。",
        stream=True,
        stream_events=True,
    )

    saw_tool = False
    saw_reasoning = False

    for event in response:
        event_name = getattr(event, "event", "") or ""
        if event_name in {TeamRunEvent.tool_call_started.value, RunEvent.tool_call_started.value}:
            saw_tool = True
        if event_name in {
            TeamRunEvent.reasoning_started.value,
            RunEvent.reasoning_started.value,
            TeamRunEvent.reasoning_step.value,
            RunEvent.reasoning_step.value,
            TeamRunEvent.reasoning_content_delta.value,
            RunEvent.reasoning_content_delta.value,
            TeamRunEvent.reasoning_completed.value,
            RunEvent.reasoning_completed.value,
        }:
            saw_reasoning = True
        if saw_tool and saw_reasoning:
            break

    assert saw_tool
    assert saw_reasoning
