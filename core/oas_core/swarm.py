"""LangGraph Swarm builder — wraps langgraph-swarm for DarkLab agents.

Converts existing DarkLab agent handlers into LangGraph nodes with
dynamic handoff via tool calls.  Preserves the existing `ROUTING_TABLE`
as a fast-path while enabling LLM-driven routing for free-form requests.

Requires ``oas-core[swarm]`` optional dependencies (langgraph, langgraph-swarm,
langchain-anthropic). If not installed, ``SWARM_AVAILABLE`` is False and
``build_swarm()`` raises ImportError.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Awaitable

logger = logging.getLogger("oas.swarm")

# Import guard — LangGraph is optional
try:
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    from langgraph.graph import StateGraph, END, START
    from langgraph.graph.message import MessagesState
    from langgraph.prebuilt import ToolNode
    from langgraph.checkpoint.memory import MemorySaver as InMemorySaver
    from langgraph_swarm import SwarmState, create_handoff_tool, add_active_agent_router

    SWARM_AVAILABLE = True
except ImportError:
    SWARM_AVAILABLE = False

__all__ = ["build_swarm", "wrap_agent_as_node", "SWARM_AVAILABLE"]


if SWARM_AVAILABLE:
    class DarkLabSwarmState(SwarmState):
        """Extended swarm state with request_id for DRVP propagation."""
        request_id: str = ""


def wrap_agent_as_node(
    handler: Callable[..., Awaitable[Any]],
    agent_name: str,
    task_type_value: str,
    device: str,
) -> Callable:
    """Wrap a DarkLab ``handle(task) -> TaskResult`` function as a
    LangGraph node that reads/writes ``SwarmState.messages``.

    The wrapper:
    1. Emits DRVP HANDOFF_COMPLETED event
    2. Extracts the last HumanMessage as task text
    3. Builds a Task with appropriate TaskType
    4. Calls the DarkLab handler
    5. Returns the result as an AIMessage
    """
    if not SWARM_AVAILABLE:
        raise ImportError(
            "langgraph-swarm not installed. Run: uv pip install 'oas-core[swarm]'"
        )

    async def node_fn(state: dict) -> dict:
        # Late imports to avoid requiring cluster packages in core at import time
        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

        request_id = state.get("request_id", "") or uuid.uuid4().hex[:12]

        # Emit HANDOFF_COMPLETED — this agent just received control
        try:
            await emit(DRVPEvent(
                event_type=DRVPEventType.HANDOFF_COMPLETED,
                request_id=request_id,
                agent_name=agent_name,
                device=device,
                payload={"from_agent": "leader"},
            ))
        except Exception:
            pass  # DRVP is best-effort

        # Extract text from last human message
        messages = state.get("messages", [])
        text = ""
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human":
                text = msg.content if isinstance(msg.content, str) else str(msg.content)
                break

        # Build Task and call handler
        # Import models inline — handler may supply its own Task import
        import importlib
        models = importlib.import_module("shared.models") if _is_cluster_context() else None

        task_id = uuid.uuid4().hex[:12]

        if models:
            task = models.Task(
                task_id=task_id,
                task_type=models.TaskType(task_type_value),
                payload={"text": text},
            )
        else:
            # Fallback: construct a dict-like Task if shared.models not available
            from pydantic import BaseModel
            task = type("Task", (), {
                "task_id": task_id,
                "task_type": task_type_value,
                "payload": {"text": text},
                "user_id": 0,
            })()

        try:
            result = await handler(task)
            if hasattr(result, "model_dump_json"):
                content = result.model_dump_json()
            else:
                import json
                content = json.dumps(result if isinstance(result, dict) else {"result": str(result)})
        except Exception as exc:
            logger.error("agent_node_error", extra={"agent": agent_name, "error": str(exc)})
            content = f'{{"error": "{exc}", "agent": "{agent_name}", "status": "error"}}'

        return {"messages": [AIMessage(content=content, name=agent_name)]}

    node_fn.__name__ = agent_name
    return node_fn


def _is_cluster_context() -> bool:
    """Check if shared.models is importable (running in cluster context)."""
    try:
        import shared.models  # noqa: F401
        return True
    except ImportError:
        return False


def build_swarm(
    agent_registry: dict[str, dict],
    default_active: str = "leader",
    *,
    anthropic_api_key: str | None = None,
    model: str = "claude-sonnet-4-6-20260301",
) -> Any:
    """Build a LangGraph StateGraph for DarkLab swarm routing.

    Parameters
    ----------
    agent_registry : dict
        Mapping of agent name → {"handler", "task_type", "device", "description"}.
    default_active : str
        Name of the default agent (usually "leader").
    anthropic_api_key : str | None
        API key for the leader LLM node.
    model : str
        Anthropic model for the leader router.

    Returns
    -------
    CompiledStateGraph
        A compiled LangGraph that can be invoked with ``.ainvoke()``.
    """
    if not SWARM_AVAILABLE:
        raise ImportError(
            "langgraph-swarm not installed. Run: uv pip install 'oas-core[swarm]'"
        )

    from langchain_anthropic import ChatAnthropic

    # Build handoff tools — one per agent in the registry
    handoff_tools = []
    for name, spec in agent_registry.items():
        tool = create_handoff_tool(
            agent_name=name,
            description=spec["description"],
        )
        handoff_tools.append(tool)

    # Leader LLM node — the intelligent router
    llm = ChatAnthropic(
        model=model,
        api_key=anthropic_api_key,
    ).bind_tools(handoff_tools)

    # Build the agent description list for the system prompt
    agent_descriptions = "\n".join(
        f"- **{name}** ({spec['device']}): {spec['description']}"
        for name, spec in agent_registry.items()
    )

    leader_system = f"""\
You are the DarkLab Leader, an AI research orchestrator for the Opensens distributed lab.

Analyze the user's research request and route it to the most appropriate specialist agent
by calling the corresponding transfer tool. Only transfer to ONE agent per turn.

Available agents:
{agent_descriptions}

Choose the agent whose capabilities best match the request. If the request spans multiple
agents, start with the most relevant one — subsequent steps will be handled in follow-up turns.
"""

    async def leader_node(state: dict) -> dict:
        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

        request_id = state.get("request_id", "") or uuid.uuid4().hex[:12]

        try:
            await emit(DRVPEvent(
                event_type=DRVPEventType.AGENT_ACTIVATED,
                request_id=request_id,
                agent_name="leader",
                device="leader",
                payload={"n_messages": len(state.get("messages", []))},
            ))
        except Exception:
            pass

        msgs = [SystemMessage(content=leader_system)] + state.get("messages", [])
        response = await llm.ainvoke(msgs)

        # Emit HANDOFF_STARTED for tool calls
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                target = tc.get("name", "").replace("transfer_to_", "")
                try:
                    await emit(DRVPEvent(
                        event_type=DRVPEventType.HANDOFF_STARTED,
                        request_id=request_id,
                        agent_name="leader",
                        device="leader",
                        payload={"to_agent": target, "tool_call_id": tc.get("id", "")},
                    ))
                except Exception:
                    pass

        return {"messages": [response]}

    # Build the graph
    builder = StateGraph(DarkLabSwarmState)

    # Leader node (LLM router)
    builder.add_node("leader", leader_node)

    # Tool node for handoff execution
    tool_node = ToolNode(handoff_tools)
    builder.add_node("tools", tool_node)

    # Agent nodes
    for name, spec in agent_registry.items():
        node_fn = wrap_agent_as_node(
            handler=spec["handler"],
            agent_name=name,
            task_type_value=spec["task_type"],
            device=spec["device"],
        )
        builder.add_node(name, node_fn)
        # After agent completes, return to leader for synthesis/next step
        builder.add_edge(name, "leader")

    # Leader routing: tool_calls → tools node, else END
    def route_leader(state: dict) -> str:
        messages = state.get("messages", [])
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                return "tools"
        return END

    builder.add_conditional_edges("leader", route_leader, ["tools", END])

    # START routing via active_agent field
    all_node_names = ["leader"] + list(agent_registry.keys())
    add_active_agent_router(
        builder,
        route_to=all_node_names,
        default_active_agent=default_active,
    )

    # Tools node has edges handled by Command objects from handoff tools
    # Fallback edge if no Command redirect occurs
    builder.add_edge("tools", "leader")

    return builder.compile(checkpointer=InMemorySaver())
