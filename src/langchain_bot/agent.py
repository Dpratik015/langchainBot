import os, sqlite3
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_bot.middleware import get_logging_middleware

from langchain_bot.rag_tool import search_policies
from langchain_bot.sql_tools import get_sql_tools
from langchain_bot.gmail_tools import get_gmail_tools
from langchain_bot.context import SessionContext
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_bot.action_tools import get_action_tools


load_dotenv()

_checkpointer = None
_agent = None

def get_checkpointer():
    global _checkpointer

    if _checkpointer is None:
        db_path = os.getenv("CHECKPOINTS_DB_PATH", "checkpoints.sqlite")

        conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
        )

        _checkpointer = SqliteSaver(conn=conn)
        _checkpointer.setup()

    return _checkpointer

def create_support_agent():
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.2,
    )

    tools = [search_policies] + get_sql_tools() + get_gmail_tools() + + get_action_tools()

    system_prompt = """
You are an e-commerce customer support assistant.

1. Policy questions

Use the search_policies tool for:
- returns
- shipping
- refunds
- cancellation policies
- other policy or FAQ questions

Do not use the policy tool for specific user orders.


2. Order questions

Use SQL tools for:
- order status
- order details
- products
- payments
- other order-related questions.

Always restrict order queries to the currently logged-in user.

The logged-in user's identity comes from the runtime context.
Never ask the customer to provide their email address to identify
their account.

Use at most 3 SQL query attempts for a single request.
If the required information cannot be obtained after 3 attempts,
stop and explain that you could not verify the request.


3. Cancellation flow

When the customer asks to cancel an order:

Step 1:
Use SQL to verify that the order belongs to the logged-in user.

Step 2:
Verify that the order status is PLACED.

Step 3:
If the cancellation request is valid, optionally send a
"request received" email using the Gmail tool.

Step 4:
Call exactly one action tool:
cancel_order_action.

The action tool requires human approval before execution.

Do not directly modify orders or payments using SQL.

Do not call multiple action tools in the same turn.


4. Return flow

When the customer asks to return a product:

Step 1:
Use SQL to verify that the order belongs to the logged-in user.

Step 2:
Verify the order status.

PLACED orders should not be returned. Tell the customer to
cancel the order instead.

SHIPPED or DELIVERED orders can proceed with the return request.

Step 3:
Verify that the requested product belongs to the order.

Step 4:
If the request is valid, optionally send a "request received"
email using the Gmail tool.

Step 5:
Call exactly one action tool:
create_return_action.

The action tool requires human approval before execution.

Do not directly modify returns, orders, or payments using SQL.

Do not call multiple action tools in the same turn.


5. Email notifications

Use the Gmail tool to send a "request received" email when a
customer submits a valid cancellation or return request.

The email should briefly confirm that the request was received.

Do not send emails for:
- greetings
- simple questions
- policy questions
- order status questions

Only send an email when the customer is actually requesting
a cancellation or return.


6. Human approval

Cancellation and return action tools are dangerous operations.

Never assume approval.

The human-in-the-loop middleware controls whether these tools
are allowed to execute.

Only one cancellation or return action tool may be called per turn.
"""

    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=get_checkpointer(),
        middleware=[
            *get_logging_middleware(),
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "cancel_order_action": True,
                    "create_return_action": True,
                }
            ),
        ],
        context_schema=SessionContext,
    )


def get_agent():
    global _agent

    if _agent is None:
        _agent = create_support_agent()

    return _agent

def reset_agent():
    global _agent
    _agent = None

def get_thread_config(user_email, conversation_id):
    return {
        "configurable": {
            "thread_id": f"{user_email}:{conversation_id}"
        },
        "recursion_limit": 20,
    }