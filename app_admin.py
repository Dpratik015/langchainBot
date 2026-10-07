import streamlit as st

from langchain_bot.auth import authenticate_user
from langchain_bot.hitl_utils import (
    list_pending_actions,
    resume_with_decision,
)


st.set_page_config(
    page_title="E-commerce Admin",
    page_icon="🔐",
    layout="wide",
)


def init_admin_session():
    st.session_state.setdefault(
        "admin_email",
        None,
    )

    st.session_state.setdefault(
        "admin_role",
        None,
    )


def admin_login():
    st.title("Admin Dashboard")

    email = st.text_input(
        "Email",
        key="admin_email_input",
    )

    password = st.text_input(
        "Password",
        type="password",
        key="admin_password_input",
    )

    if st.button("Login"):
        user = authenticate_user(
            email,
            password,
            role="admin",
        )

        if user:
            st.session_state.admin_email = user["email"]
            st.session_state.admin_role = user["role"]
            st.rerun()
        else:
            st.error("Invalid admin credentials.")


def dashboard():
    st.title("Human-in-the-loop Admin Dashboard")

    st.sidebar.success(
        f"Logged in as {st.session_state.admin_email}"
    )

    if st.sidebar.button("Logout"):
        st.session_state.admin_email = None
        st.session_state.admin_role = None
        st.rerun()

    st.header("Pending Actions")

    status = st.selectbox(
        "Status",
        [
            "PENDING",
            "APPROVED",
            "REJECTED",
        ],
    )

    email_filter = st.text_input(
        "Filter by customer email",
    )

    actions = list_pending_actions(status=status)

    if email_filter:
        actions = [
            action
            for action in actions
            if email_filter.lower()
            in action["user_email"].lower()
        ]

    if not actions:
        st.info("No matching actions.")
        return

    for action in actions:
        with st.container(border=True):
            st.subheader(
                f"{action['action_type']} — "
                f"Order {action['order_id']}"
            )

            col1, col2 = st.columns(2)

            with col1:
                st.write(
                    f"**Customer:** {action['user_email']}"
                )
                st.write(
                    f"**Order ID:** {action['order_id']}"
                )
                st.write(
                    f"**Action:** {action['action_type']}"
                )

            with col2:
                st.write(
                    f"**Thread:** {action['thread_id']}"
                )
                st.write(
                    f"**Product:** "
                    f"{action['product_name'] or '-'}"
                )
                st.write(
                    f"**Reason:** "
                    f"{action['reason'] or '-'}"
                )

            if action["status"] == "PENDING":

                approve_col, reject_col = st.columns(2)

                with approve_col:
                    if st.button(
                        "Approve",
                        key=f"approve_{action['id']}",
                        type="primary",
                    ):
                        try:
                            result = resume_with_decision(
                                action["id"],
                                "approve",
                            )

                            st.success(
                                "Request approved and processed."
                            )

                            if result:
                                st.write(result)

                            st.rerun()

                        except Exception as exc:
                            st.error(
                                f"Approval failed: {exc}"
                            )

                with reject_col:
                    if st.button(
                        "Reject",
                        key=f"reject_{action['id']}",
                    ):
                        try:
                            result = resume_with_decision(
                                action["id"],
                                "reject",
                            )

                            st.warning(
                                "Request rejected."
                            )

                            if result:
                                st.write(result)

                            st.rerun()

                        except Exception as exc:
                            st.error(
                                f"Rejection failed: {exc}"
                            )


init_admin_session()

if not st.session_state.admin_email:
    admin_login()
else:
    dashboard()