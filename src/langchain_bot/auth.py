from pathlib import Path
import sqlite3
from typing import TypedDict


class UserRecord(TypedDict):
    email: str
    full_name: str
    role: str


def authenticate_user(email: str, password: str, role: str | None = None, ) -> UserRecord | None:
    root = Path(__file__).resolve().parents[2]
    db_path = root / "ecommerce.db"

    query = """
        SELECT email, full_name, role
        FROM users
        WHERE email = ? AND password = ?
    """

    params: list[str] = [email, password]

    if role is not None:
        query += " AND role = ?"
        params.append(role)

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(query, params).fetchone()

    if row is None:
        return None

    return {
        "email": row[0],
        "full_name": row[1],
        "role": row[2],
    }