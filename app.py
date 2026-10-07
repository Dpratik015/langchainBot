import json
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from uuid import uuid4
from langchain_bot.auth import authenticate_user
from langchain_bot.agent import get_agent, reset_agent
from langchain_bot.agent import get_thread_config
from langchain_bot.rag_tool import initialize_vector_store
from langchain_bot.gmail_tools import initialize_gmail, is_gmail_available
from langchain_bot.context import SessionContext
from langchain_bot.context import SessionContext
from langchain_bot.hitl_utils import handle_interrupt

def get_llm():
    return ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

def build_chain(llm):
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a concise, helpful assistant. Use prior chat history to stay on context."),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}")
    ])

    return prompt | llm


def init_session():
    st.session_state.setdefault("user_email", None)
    st.session_state.setdefault("user_role", None)
    st.session_state.setdefault("conversation_id", None)
    st.session_state.setdefault("vector_store_ready", False)
    st.session_state.setdefault("gmail_initialized", False)
    st.session_state.setdefault("hitl_message", None)

def render_history():
    user_email = st.session_state.user_email
    conversation_id = st.session_state.conversation_id

    if not user_email or not conversation_id:
        return

    config = get_thread_config(
        user_email,
        conversation_id,
    )

    snapshot = get_agent().get_state(config)

    for msg in snapshot.values.get("messages", []):
        if msg.type == "human":
            with st.chat_message("user"):
                st.markdown(msg.content)

        elif msg.type == "ai" and msg.content:
            with st.chat_message("assistant"):
                st.markdown(msg.content)


def chat_round(user_input):
    user_email = st.session_state.user_email
    conversation_id = st.session_state.conversation_id

    config = get_thread_config(
        user_email,
        conversation_id,
    )

    context = SessionContext(
        user_email=user_email,
        conversation_id=conversation_id,
        role=st.session_state.user_role or "customer",
    )

    get_agent().invoke(
        {"messages": [{"role": "user", "content": user_input}]},
        config=config,
        context=context,
)
    interrupt_message = handle_interrupt(
       result,
       user_email,
       conversation_id,
    )

    if interrupt_message:
        st.session_state["hitl_message"] = interrupt_message

    st.rerun()

def start_new_conversation():
    conversation_id = str(uuid4())

    add_thread(
        st.session_state.user_email,
        conversation_id,
    )

    st.session_state.conversation_id = conversation_id

def load_conversation(conv_id):
    conversations = st.session_state.conversations

    if conv_id in conversations:
        st.session_state.conversation_id = conv_id
        st.session_state.messages = conversations[conv_id].copy()


THREADS_PATH = Path(__file__).resolve().parent / "chat_threads.json"


def load_threads(user_email):
    if not THREADS_PATH.exists():
        return []

    with THREADS_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return data.get(user_email, [])


def save_threads(user_email, threads):
    data = {}

    if THREADS_PATH.exists():
        with THREADS_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)

    data[user_email] = threads

    with THREADS_PATH.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def add_thread(user_email, conversation_id):
    threads = load_threads(user_email)

    threads.append({
        "id": conversation_id,
        "label": f"Chat {conversation_id[:8]}",
    })

    save_threads(user_email, threads)
    
def main():
    st.set_page_config(page_title="LangChain Bot", page_icon="🤖")
    st.title("LangChain Bot")
    st.caption("This bot is for help!")
    load_dotenv()
    init_session()

    if not st.session_state.gmail_initialized:
        initialize_gmail()
        reset_agent()
        st.session_state.gmail_initialized = True

    if not st.session_state.vector_store_ready:
        with st.spinner("Initializing knowledge base..."):
            try:
                initialize_vector_store()
                st.session_state.vector_store_ready = True
            except Exception as exc:
                st.error(f"Failed to initialize knowledge base: {exc}")
                st.stop()

    
    user_email = st.session_state.user_email

    if not user_email:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            role = st.selectbox("Role", ["customer", "admin"])
            login = st.form_submit_button("Login")

            if login:
                user = authenticate_user(email, password, role)

                if user:
                    st.session_state.user_email = user["email"]
                    st.session_state.user_role = user["role"]

                    threads = load_threads(user["email"])

                    if threads:
                       st.session_state.conversation_id = threads[0]["id"]
                    else:
                        conversation_id = str(uuid4())
                        add_thread(user["email"], conversation_id)
                        st.session_state.conversation_id = conversation_id

                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid email, password, or role.")

        return

    
    with st.sidebar:
        st.header("Conversations")

        if st.button("Start new conversation"):
           start_new_conversation()
           st.rerun()

        if is_gmail_available():
            st.success("Gmail: Enabled")
        else:
            st.warning("Gmail: Not configured")

        threads = load_threads(st.session_state.user_email)

        if threads:
            thread_ids = [thread["id"] for thread in threads]
            thread_labels = {
                thread["id"]: thread["label"]
                for thread in threads
            }
    
            selected_id = st.selectbox(
                "Select conversation",
                thread_ids,
                index=thread_ids.index(
                    st.session_state.conversation_id
                ),
                format_func=lambda thread_id: thread_labels[thread_id],
            )
    
            if selected_id != st.session_state.conversation_id:
                st.session_state.conversation_id = selected_id
                st.rerun()

        else:
            st.selectbox(
                "Select conversation",
                ["(no threads yet)"],
                disabled=True,
            )

    
    conversation_id = st.session_state.conversation_id or "—"

    st.info(
        f"Logged in as: {st.session_state.user_email}  \n"
        f"Role: {st.session_state.user_role}  \n"
        f"Conversation: {conversation_id}"
    )

    render_history()

    if st.session_state.get("hitl_message"):
        st.info(st.session_state["hitl_message"])

    prompt = st.chat_input("Ask a question")

    if prompt:
            chat_round(prompt)

    st.rerun()

if __name__ == "__main__":
    main()

