# this is my # services/llm/graph.py
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from services.llm.tools import TOOLS
import os
from dotenv import load_dotenv

load_dotenv()
OPENAI_KEYS = os.getenv("OPENAI_KEYS_Demo", "[]")

memory = MemorySaver()


class GraphState(TypedDict):
    messages: Annotated[list, add_messages]


def build_llm_graph(llm_with_tools):
    # -----------------------------
    # NODE: main LLM
    # -----------------------------
    def llm_node(state: GraphState):
        return {"messages": [llm_with_tools.invoke(state["messages"])]}

    # -----------------------------
    # NODE: summarizer (≤100 words)
    # -----------------------------
    def summary_node(state: GraphState):
        last_ai = next(
            (msg for msg in reversed(state.get("messages", [])) if isinstance(msg, AIMessage)),
            None,
        )
        if last_ai is None:
            return {"messages": []}

        content = last_ai.content
        if isinstance(content, list):
            content = "".join(
                chunk.get("text", "")
                for chunk in content
                if isinstance(chunk, dict) and chunk.get("type") == "text"
            )
        elif not isinstance(content, str):
            content = str(content)

        summarizer = ChatOpenAI(
            model="gpt-4.1-mini",
            temperature=0,
            api_key=OPENAI_KEYS,
        )

        summary_prompt = [
            SystemMessage(
                   content=(
                    "You are an EXTRACTIVE summarizer.\n"
                    "\n"
                    "STRICT RULES:\n"
                    "1) If the assistant reply is ≤ 100 words: return it EXACTLY as-is (verbatim). "
                    "   Do not change wording, casing, punctuation, or order.\n"
                    "2) If it is > 100 words: produce a ≤ 100-word EXTRACTIVE summary using ONLY text "
                    "   copied from the original reply. You may delete sentences/phrases, but you may "
                    "   not invent, rephrase, incomplete sentances or add pleasantries.\n"
                    "3) Never add any new sentence not present in the original. "
                    "   Do NOT address the user or change the speaker’s identity.\n"
                    "4) If the reply includes structured data (client codes, IDs, JSON, lists, tables, bullets): "
                    "   copy that DATA verbatim and only trim surrounding prose. Do NOT truncate, mask, or summarize the data itself. It is allowed for the final output to approach the word limit due to data blocks.\n"
                    "5)  If the reply appears incomplete or cut off, complete only the current sentence "
                        "so that it becomes grammatically complete — do not add new information.\n"
                        "\n"
                    "Output: plain text only, no meta commentary."
                )
            ),
            HumanMessage(content=content.strip()),
        ]

        summary_msg = summarizer.invoke(summary_prompt)
        if not isinstance(summary_msg, AIMessage):
            summary_msg = AIMessage(content=str(summary_msg))
        return {"messages": [summary_msg]}

    # -----------------------------
    # NODE: router (checks word count)
    # -----------------------------
    def router_node(state: GraphState):
        return {}  # no state modification

    def route_after_llm(state: GraphState) -> str:
        last_ai = next(
            (m for m in reversed(state.get("messages", [])) if isinstance(m, AIMessage)),
            None,
        )
        if not last_ai:
            return "__end__"

        text = str(last_ai.content).strip()
        return "summary" if len(text.split()) > 100 else "__end__"


    # -----------------------------
    # BUILD GRAPH
    # -----------------------------
    builder = StateGraph(GraphState)
    builder.add_node("llm", llm_node)
    builder.add_node("tools", ToolNode(TOOLS))
    # builder.add_node(
    #     "tools",
    #     ToolNode(
    #         tools=list(TOOLS.values()),
    #         parallel_tool_calls=True,
    #     ),
    # )
    builder.add_node("router", router_node)
    builder.add_node("summary", summary_node)

    # START → llm
    builder.add_edge(START, "llm")
    builder.add_conditional_edges("llm",tools_condition, {"tools": "tools","__end__": "router",}) # If tools used → tools → llm → router
    builder.add_edge("tools", "llm") # If no tools → llm → router
    builder.add_conditional_edges("router",route_after_llm,{"summary": "summary","__end__": "__end__",},)

    builder.add_edge("summary", END)

    graph_new = builder.compile(checkpointer=memory)

    # Optional: save visual diagram
    # try:
    #     g = graph_new.get_graph()
    #     png_bytes = g.draw_mermaid_png()
    #     with open("nyla_graph.png", "wb") as f:
    #         f.write(png_bytes)
    #     print(" LangGraph image saved: nyla_graph.png")
    # except Exception as e:
    #     print(f" Could not generate graph image: {e}")

    return graph_new
