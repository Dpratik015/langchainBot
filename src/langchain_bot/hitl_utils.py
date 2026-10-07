from pathlib import Path
import sqlite3
from datetime import datetime

from langgraph.types import Command

from langchain_bot.agent import get_agent
from langchain_bot.context import SessionContext


def get_database_path():
    root = Path(__file__).resolve().parents[2]
    return root / "ecommerce.db"


def list_pending_actions(status="PENDING"):
    """Return pending HITL actions."""

    db_path = get_database_path()

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                id,
                thread_id,
                user_email,
                action_type,
                order_id,
                product_name,
                reason,
                status,
                created_at,
                updated_at
            FROM pending_actions
            WHERE status = ?
            ORDER BY created_at ASC
            """,
            (status,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_pending_action(action_id):
    """Get one pending action."""

    db_path = get_database_path()

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row

        row = connection.execute(
            """
            SELECT
                id,
                thread_id,
                user_email,
                action_type,
                order_id,
                product_name,
                reason,
                status,
                created_at,
                updated_at
            FROM pending_actions
            WHERE id = ?
            """,
            (action_id,),
        ).fetchone()

    return dict(row) if row else None


def has_pending_action(thread_id, action_type, order_id):
    """Prevent duplicate pending requests."""

    db_path = get_database_path()

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT id
            FROM pending_actions
            WHERE thread_id = ?
              AND action_type = ?
              AND order_id = ?
              AND status = 'PENDING'
            LIMIT 1
            """,
            (
                thread_id,
                action_type,
                order_id,
            ),
        ).fetchone()

    return row is not None


def _insert_pending_action(
    thread_id,
    user_email,
    action_type,
    order_id,
    product_name=None,
    reason=None,
):
    """Insert a pending action unless the same one already exists."""

    if has_pending_action(
        thread_id,
        action_type,
        order_id,
    ):
        return False

    db_path = get_database_path()

    now = datetime.now().isoformat()

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO pending_actions (
                thread_id,
                user_email,
                action_type,
                order_id,
                product_name,
                reason,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
            """,
            (
                thread_id,
                user_email,
                action_type,
                order_id,
                product_name,
                reason,
                now,
                now,
            ),
        )

        connection.commit()

    return True


def _extract_interrupts(result):
    """
    Extract LangGraph HITL interrupt payloads.

    HumanInTheLoopMiddleware places interrupt information in
    the agent result under __interrupt__.
    """

    if not result:
        return []

    interrupts = result.get("__interrupt__", [])

    if interrupts is None:
        return []

    if not isinstance(interrupts, (list, tuple)):
        interrupts = [interrupts]

    return list(interrupts)


def _extract_request_from_interrupt(interrupt):
    """
    Extract action request information from a HITL interrupt.
    """

    value = getattr(interrupt, "value", interrupt)

    if isinstance(value, dict):
        request = value.get("action_requests")

        if request is None:
            request = value.get("action_request")

        if request is None:
            request = value.get("request")

        if isinstance(request, list):
            request = request[0] if request else None

        if isinstance(request, dict):
            return request

        return value

    return {}


def handle_interrupt(
    result,
    user_email,
    conversation_id,
):
    """
    Detect HITL interrupts, store pending business actions,
    and return a message for the customer UI.

    Returns:
        str | None
    """

    interrupts = _extract_interrupts(result)

    if not interrupts:
        return None

    pending_count = 0

    for interrupt in interrupts:
        request = _extract_request_from_interrupt(interrupt)

        tool_name = (
            request.get("name")
            or request.get("tool_name")
            or request.get("tool")
        )

        arguments = (
            request.get("args")
            or request.get("arguments")
            or {}
        )

        if tool_name == "cancel_order_action":
            action_type = "CANCELLATION"

        elif tool_name == "create_return_action":
            action_type = "RETURN"

        else:
            continue

        order_id = arguments.get("order_id")

        if order_id is None:
            continue

        inserted = _insert_pending_action(
            thread_id=f"{user_email}:{conversation_id}",
            user_email=user_email,
            action_type=action_type,
            order_id=order_id,
            product_name=arguments.get("product_name"),
            reason=arguments.get("reason"),
        )

        if inserted:
            pending_count += 1

    if pending_count:
        return (
            "### Request pending approval\n\n"
            "Your request has been submitted for admin approval. "
            "No order or payment changes have been made yet."
        )

    return (
        "### Request already pending\n\n"
        "This request is already waiting for admin approval."
    )


def resume_with_decision(
    action_id,
    decision,
):
    """
    Resume the exact LangGraph thread after an admin decision.

    decision must be 'approve' or 'reject'.
    """

    if decision not in {"approve", "reject"}:
        raise ValueError(
            "decision must be 'approve' or 'reject'"
        )

    pending = get_pending_action(action_id)

    if pending is None:
        raise ValueError(
            f"Pending action {action_id} was not found."
        )

    if pending["status"] != "PENDING":
        raise ValueError(
            f"Pending action {action_id} is already "
            f"{pending['status']}."
        )

    thread_id = pending["thread_id"]
    user_email = pending["user_email"]

    conversation_id = thread_id.split(":", 1)[1]

    context = SessionContext(
        user_email=user_email,
        conversation_id=conversation_id,
        role="customer",
    )

    config = {
        "configurable": {
            "thread_id": thread_id,
        },
        "recursion_limit": 20,
    }

    if decision == "approve":
        resume_value = {
            "decisions": [
                {
                    "type": "approve",
                }
            ]
        }

    else:
        resume_value = {
            "decisions": [
                {
                    "type": "reject",
                    "message": "The administrator rejected this request.",
                }
            ]
        }

    result = get_agent().invoke(
        Command(resume=resume_value),
        config=config,
        context=context,
    )

    new_status = (
        "APPROVED"
        if decision == "approve"
        else "REJECTED"
    )

    db_path = get_database_path()

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE pending_actions
            SET status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                new_status,
                datetime.now().isoformat(),
                action_id,
            ),
        )

        connection.commit()

    return result