from typing import TypedDict, Annotated, Optional
from langgraph.graph import add_messages, StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessageChunk, ToolMessage
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.checkpoint.memory import MemorySaver
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from uuid import uuid4
import json
import os

# Load environment variables
load_dotenv()
tavily_key = os.getenv("TAVILY_API_KEY")
groq_key = os.getenv("GROQ_API_KEY")

# Validate required API keys
if not tavily_key:
    raise ValueError("TAVILY_API_KEY not found in environment variables. Please add it to your .env file.")
if not groq_key:
    raise ValueError("GROQ_API_KEY not found in environment variables. Please add it to your .env file.")

# IP rate limiter (in-memory)
ip_cache = {}  # Format: {ip: timestamp}

# Initialize memory saver for checkpointing
memory = MemorySaver()

class State(TypedDict):
    messages: Annotated[list, add_messages]

try:
    # Initialize tools with API key
    search_tool = TavilySearchResults(max_results=4, api_key=tavily_key)
    tools = [search_tool]

    # Initialize Groq LLM with explicit API key
    llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=groq_key)
    llm_with_tools = llm.bind_tools(tools=tools)
except Exception as e:
    print(f"Error initializing AI tools: {str(e)}")
    raise

# LLM node
async def model(state: State):
    try:
        result = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [result]}
    except Exception as e:
        print(f"Error in model processing: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Router to decide next step
async def tools_router(state: State):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0:
        return "tool_node"
    return END

# Tool node handler
async def tool_node(state):
    try:
        tool_calls = state["messages"][-1].tool_calls
        tool_messages = []

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            if tool_name == "tavily_search_results_json":
                search_results = await search_tool.ainvoke(tool_args)
                tool_messages.append(
                    ToolMessage(
                        content=str(search_results),
                        tool_call_id=tool_id,
                        name=tool_name
                    )
                )

        return {"messages": tool_messages}
    except Exception as e:
        print(f"Error in tool processing: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Build graph
graph_builder = StateGraph(State)
graph_builder.add_node("model", model)
graph_builder.add_node("tool_node", tool_node)
graph_builder.set_entry_point("model")
graph_builder.add_conditional_edges("model", tools_router)
graph_builder.add_edge("tool_node", "model")
graph = graph_builder.compile(checkpointer=memory)

# FastAPI app setup
app = FastAPI(title="AI Chatbot API")

# Allow CORS for frontend domain
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:8501")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type"],
)

@app.get("/")
async def root():
    return {"status": "healthy", "message": "AI Chatbot API is running"}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "tavily_key_configured": bool(tavily_key),
        "groq_key_configured": bool(groq_key)
    }

# Helper: Serialize AI chunk
def serialise_ai_message_chunk(chunk): 
    if isinstance(chunk, AIMessageChunk):
        return chunk.content
    raise TypeError(f"Unsupported type: {type(chunk).__name__}")

# Streamed response generator
async def generate_chat_responses(message: str, checkpoint_id: Optional[str] = None):
    try:
        is_new_conversation = checkpoint_id is None

        if is_new_conversation:
            new_checkpoint_id = str(uuid4())
            config = {"configurable": {"thread_id": new_checkpoint_id}}
            events = graph.astream_events({"messages": [HumanMessage(content=message)]}, version="v2", config=config)
            yield f"data: {{\"type\": \"checkpoint\", \"checkpoint_id\": \"{new_checkpoint_id}\"}}\n\n"
        else:
            config = {"configurable": {"thread_id": checkpoint_id}}
            events = graph.astream_events({"messages": [HumanMessage(content=message)]}, version="v2", config=config)

        async for event in events:
            event_type = event["event"]

            if event_type == "on_chat_model_stream":
                chunk_content = serialise_ai_message_chunk(event["data"]["chunk"])
                yield f"data: {json.dumps({'type': 'content', 'content': chunk_content})}\n\n"

            elif event_type == "on_chat_model_end":
                tool_calls = getattr(event["data"]["output"], "tool_calls", [])
                for call in tool_calls:
                    if call["name"] == "tavily_search_results_json":
                        query = call["args"].get("query", "")
                        yield f"data: {json.dumps({'type': 'search_start', 'query': query})}\n\n"

            elif event_type == "on_tool_end" and event["name"] == "tavily_search_results_json":
                output = event["data"]["output"]
                if isinstance(output, list):
                    urls = [item["url"] for item in output if isinstance(item, dict) and "url" in item]
                    yield f"data: {{\"type\": \"search_results\", \"urls\": {json.dumps(urls)}}}\n\n"

        yield f"data: {json.dumps({'type': 'end'})}\n\n"
    except Exception as e:
        error_message = str(e)
        print(f"Error in chat generation: {error_message}")
        yield f"data: {json.dumps({'type': 'error', 'message': error_message})}\n\n"

# Main endpoint with IP-based limiter
@app.get("/chat_stream/{message}")
async def chat_stream(message: str, request: Request, checkpoint_id: Optional[str] = Query(None)):
    try:
        ip = request.client.host

        # # Track how many requests this IP has made
        # if ip not in ip_cache:
        #     ip_cache[ip] = {"count": 1}
        # else:
        #     ip_cache[ip]["count"] += 1

        # # Deny if more than 3 requests
        # if ip_cache[ip]["count"] > 3:
        #     apology_message = {
        #         "type": "limit",
        #         "message": "❗ Request limit reached. Only 3 requests per user are allowed."
        #     }
        #     return StreamingResponse(
        #         iter([f"data: {json.dumps(apology_message)}\n\n"]),
        #         media_type="text/event-stream"
        #     )

        # Allow the request
        return StreamingResponse(
            generate_chat_responses(message, checkpoint_id),
            media_type="text/event-stream"
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")  # Default to localhost for development
    uvicorn.run("main:app", host=host, port=port, reload=True)  # Enable reload for development
