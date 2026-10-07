from datetime import datetime
from pathlib import Path
import sqlite3

from langchain.tools import tool, ToolRuntime

from langchain_bot.context import SessionContext


def get_database_path():
    root = Path(__file__).resolve().parents[2]
    return root / "ecommerce.db"


@tool
def cancel_order_action(
    order_id: int,
    runtime: ToolRuntime[SessionContext],
) -> str:
    """Cancel a customer's PLACED order after admin approval."""

    user_email = runtime.context.user_email
    thread_id = runtime.context.conversation_id

    db_path = get_database_path()

    with sqlite3.connect(db_path) as connection:
        # Verify that the order belongs to the logged-in user
        row = connection.execute(
            """
            SELECT o.id, o.status, u.id
            FROM orders o
            JOIN users u ON u.id = o.user_id
            WHERE o.id = ? AND u.email = ?
            """,
            (order_id, user_email),
        ).fetchone()

        if row is None:
            return "Order not found or it does not belong to the logged-in user."

        _, order_status, user_id = row

        # Cancellation is allowed only for PLACED orders.
        if order_status != "PLACED":
            return (
                f"Order {order_id} cannot be cancelled because "
                f"its current status is {order_status}."
            )

        now = datetime.now().isoformat()

        # Update order
        connection.execute(
            """
            UPDATE orders
            SET status = 'CANCELLED'
            WHERE id = ?
            """,
            (order_id,),
        )

        # Refund payment
        connection.execute(
            """
            UPDATE payments
            SET status = 'REFUNDED'
            WHERE order_id = ?
            """,
            (order_id,),
        )

        # Create support ticket
        connection.execute(
            """
            INSERT INTO tickets (
                user_id,
                return_id,
                subject,
                status,
                thread_id,
                user_email,
                created_at,
                updated_at
            )
            VALUES (?, NULL, ?, 'RESOLVED', ?, ?, ?, ?)
            """,
            (
                user_id,
                f"Order {order_id} cancellation",
                thread_id,
                user_email,
                now,
                now,
            ),
        )

        connection.commit()

    return (
        f"Order {order_id} has been cancelled successfully. "
        "The payment has been marked as refunded."
    )


@tool
def create_return_action(
    order_id: int,
    product_name: str,
    reason: str,
    runtime: ToolRuntime[SessionContext],
) -> str:
    """Create a return for a SHIPPED or DELIVERED order after admin approval."""

    user_email = runtime.context.user_email
    thread_id = runtime.context.conversation_id

    db_path = get_database_path()

    with sqlite3.connect(db_path) as connection:
        # Verify ownership and order status.
        order_row = connection.execute(
            """
            SELECT o.id, o.status, u.id
            FROM orders o
            JOIN users u ON u.id = o.user_id
            WHERE o.id = ? AND u.email = ?
            """,
            (order_id, user_email),
        ).fetchone()

        if order_row is None:
            return "Order not found or it does not belong to the logged-in user."

        _, order_status, user_id = order_row

        if order_status == "PLACED":
            return (
                f"Order {order_id} is still PLACED. "
                "Please cancel the order instead of creating a return."
            )

        if order_status not in ("SHIPPED", "DELIVERED"):
            return (
                f"Order {order_id} cannot be returned because "
                f"its current status is {order_status}."
            )

        # Find the requested product in the order.
        item_row = connection.execute(
            """
            SELECT oi.id
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = ?
              AND p.name = ?
            """,
            (order_id, product_name),
        ).fetchone()

        if item_row is None:
            return (
                f"Product '{product_name}' was not found in order "
                f"{order_id}."
            )

        order_item_id = item_row[0]
        now = datetime.now().isoformat()

        # Create return request.
        cursor = connection.execute(
            """
            INSERT INTO returns (
                order_id,
                order_item_id,
                user_id,
                reason,
                status,
                requested_at
            )
            VALUES (?, ?, ?, ?, 'APPROVED', ?)
            """,
            (
                order_id,
                order_item_id,
                user_id,
                reason,
                now,
            ),
        )

        return_id = cursor.lastrowid

        # Refund payment.
        connection.execute(
            """
            UPDATE payments
            SET status = 'REFUNDED'
            WHERE order_id = ?
            """,
            (order_id,),
        )

        # Create ticket.
        connection.execute(
            """
            INSERT INTO tickets (
                user_id,
                return_id,
                subject,
                status,
                thread_id,
                user_email,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, 'RESOLVED', ?, ?, ?, ?)
            """,
            (
                user_id,
                return_id,
                f"Return request for {product_name}",
                thread_id,
                user_email,
                now,
                now,
            ),
        )

        connection.commit()

    return (
        f"Return for '{product_name}' from order {order_id} "
        "has been approved and created successfully. "
        "The payment has been marked as refunded."
    )


def get_action_tools():
    return [
        cancel_order_action,
        create_return_action,
    ]