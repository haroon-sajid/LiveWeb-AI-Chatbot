import streamlit as st
import requests
import shelve
import time
import json
import os
from datetime import datetime

# Use environment variable or default to localhost
API_STREAM_URL = os.environ.get("BACKEND_URL", "http://localhost:8000/chat_stream")

st.set_page_config(page_title="Web Search AI Chatbot", page_icon="🤖", layout="wide")

# chat history path 
CHAT_HISTORY_DIR = "chat-history"  # Changed from "../backend/chat-history"
CHAT_HISTORY_FILE = os.path.join(CHAT_HISTORY_DIR, "chat_sessions")
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)


st.markdown("""
<style>
.user-message {
    margin-left: 10%;
    color: #000000;
    font-size: 16px;
}
.assistant-message {
    margin-right: 10%;
    color: #374151;
    font-size: 16px;
}
.chat-history-item {
    padding: 8px;
    border-radius: 5px;
    cursor: pointer;
    margin-bottom: 5px;
    background-color: #f3f4f6;
}
.chat-history-item:hover {
    background-color: #e5e7eb;
}
</style>
""", unsafe_allow_html=True)

def load_chat_sessions():
    try:
        with shelve.open(CHAT_HISTORY_FILE) as db:  # Use the CHAT_HISTORY_FILE constant
            return db.get("sessions", {})
    except:
        return {}

# def save_chat_sessions(sessions):
#     with shelve.open("chat_sessions") as db:
#         db["sessions"] = sessions

def save_chat_sessions(sessions, max_sessions=20):
    if len(sessions) > max_sessions:
        # Sort by timestamp, keep newest
        sorted_items = sorted(sessions.items(), key=lambda x: float(x[0]), reverse=True)
        sessions = dict(sorted_items[:max_sessions])
    with shelve.open(CHAT_HISTORY_FILE) as db:
        db["sessions"] = sessions


def create_new_session():
    session_id = str(time.time())
    session_name = f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    st.session_state.chat_sessions[session_id] = {
        "name": session_name,
        "messages": [],
        "checkpoint_id": None
    }
    st.session_state.current_session_id = session_id
    save_chat_sessions(st.session_state.chat_sessions)

def delete_session(session_id):
    if session_id in st.session_state.chat_sessions:
        del st.session_state.chat_sessions[session_id]
        if st.session_state.current_session_id == session_id:
            st.session_state.current_session_id = None
            create_new_session()
        save_chat_sessions(st.session_state.chat_sessions)

if "chat_sessions" not in st.session_state:
    st.session_state.chat_sessions = load_chat_sessions()
if "current_session_id" not in st.session_state:
    create_new_session()

with st.sidebar:
    st.markdown("## Web Search AI Chatbot")
    if st.button("New Chat"):
        create_new_session()
        st.rerun()
    st.markdown("### Chat History")
    for sid, data in sorted(st.session_state.chat_sessions.items(), key=lambda x: float(x[0]), reverse=True):
        col1, col2 = st.columns([4,1])
        with col1:
            if st.button(data["name"], key=sid):
                st.session_state.current_session_id = sid
                st.rerun()
        with col2:
            if st.button("🗑️", key="delete_"+sid):
                delete_session(sid)
                st.rerun()

st.title("Live Web Search AI Chatbot")

session = st.session_state.chat_sessions[st.session_state.current_session_id]

for msg in session["messages"]:
    role = msg["role"]
    content = msg["content"]
    avatar = "👤" if role == "user" else "🤖"
    css_class = "user-message" if role == "user" else "assistant-message"
    with st.chat_message(role, avatar=avatar):
        st.markdown(f'<div class="{css_class}">{content}</div>', unsafe_allow_html=True)

if prompt := st.chat_input("Type your message..."):
    session["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(f'<div class="user-message">{prompt}</div>', unsafe_allow_html=True)

    with st.chat_message("assistant", avatar="🤖"):
        message_placeholder = st.empty()
        full_response = ""

        try:
            stream_url = f"{API_STREAM_URL}/{prompt}"
            params = {}
            if session["checkpoint_id"]:
                params["checkpoint_id"] = session["checkpoint_id"]

            with requests.get(stream_url, params=params, stream=True) as r:
                for line in r.iter_lines():
                    if line:
                        line = line.decode("utf-8").removeprefix("data: ")
                        data = json.loads(line)
                        if data["type"] == "checkpoint":
                            session["checkpoint_id"] = data["checkpoint_id"]
                        elif data["type"] == "content":
                            full_response += data["content"]
                            message_placeholder.markdown(f'<div class="assistant-message">{full_response} |</div>', unsafe_allow_html=True)
                        elif data["type"] == "search_start":
                            message_placeholder.markdown(f"<div class='assistant-message'>🔍Searching for: {data['query']}</div>", unsafe_allow_html=True)
                        elif data["type"] == "search_results":
                            links = "<br>".join([f"<a href='{u}' target='_blank'>{u}</a>" for u in data["urls"]])
                            full_response += f"<br><div class='assistant-message'>{links}</div>"
                        elif data["type"] == "limit":
                            full_response = data["message"]
                            message_placeholder.markdown(f'<div class="assistant-message">{full_response}</div>', unsafe_allow_html=True)
                            break
                        elif data["type"] == "end":
                            break

        except Exception as e:
            st.error(f"Error: {e}")

        message_placeholder.markdown(f'<div class="assistant-message">{full_response}</div>', unsafe_allow_html=True)
        session["messages"].append({"role": "assistant", "content": full_response})
        save_chat_sessions(st.session_state.chat_sessions)
