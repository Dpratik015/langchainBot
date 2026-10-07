from datetime import datetime

from langchain.agents.middleware import (
    wrap_model_call,
    wrap_tool_call,
)


def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@wrap_model_call
def model_logging_middleware(request, handler):
    messages = request.state.get("messages", [])

    print(
        f"[{_ts()}] [MODEL] "
        f"message_count={len(messages)}"
    )

    if messages:
        last_message = messages[-1]

        print(
            f"[{_ts()}] [MODEL] "
            f"last_message={str(last_message.content)[:200]!r}"
        )

    try:
        response = handler(request)

        result = response.result

        if result:
            last_result = result[-1]

            print(
                f"[{_ts()}] [MODEL] "
                f"response={str(last_result.content)[:200]!r}"
            )

            tool_calls = getattr(last_result, "tool_calls", None)

            if tool_calls:
                print(
                    f"[{_ts()}] [MODEL] "
                    f"tool_calls={tool_calls}"
                )

        return response

    except Exception as exc:
        print(
            f"[{_ts()}] [MODEL] ERROR: {exc}"
        )
        raise


@wrap_tool_call
def tool_logging_middleware(request, handler):
    messages = request.state.get("messages", [])

    if messages:
        last_message = messages[-1]
        tool_calls = getattr(last_message, "tool_calls", None)

        if tool_calls:
            print(
                f"[{_ts()}] [TOOL] "
                f"tool_calls={tool_calls}"
            )

    try:
        response = handler(request)

        print(
            f"[{_ts()}] [TOOL] "
            f"success"
        )

        return response

    except Exception as exc:
        print(
            f"[{_ts()}] [TOOL] ERROR: {exc}"
        )
        raise


def get_logging_middleware():
    return [
        model_logging_middleware,
        tool_logging_middleware,
    ]