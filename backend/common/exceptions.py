# Copyright (c) 2026 Yash Garad. All rights reserved.

class ServiceUnavailable(Exception):
    """A backing service (LLM, database, vector store) is unreachable or failing.

    Carries a `user_message` that is SAFE to show an end user — plain, no stack
    traces, no raw connection strings — while the original technical detail
    stays in `args`/logs for operators. The orchestrator catches these to
    degrade gracefully; the API layer maps them to the user_message.
    """

    service = "system"
    user_message = "The system is temporarily unavailable. Please try again in a moment."

    def __init__(self, detail=None):
        super().__init__(detail or self.user_message)


class LLMUnavailable(ServiceUnavailable):
    service = "llm"
    user_message = (
        "The AI service is temporarily unavailable. Please try again in a moment."
    )


class DatabaseUnavailable(ServiceUnavailable):
    service = "database"
    user_message = (
        "The information service is temporarily unavailable. Please try again in a moment."
    )


class VectorStoreUnavailable(ServiceUnavailable):
    service = "vector_store"
    user_message = "Descriptive search is temporarily unavailable."


class AssistantBusy(ServiceUnavailable):
    """Every LLM slot is occupied and the queue wait expired.

    Distinct from LLMUnavailable on purpose: nothing is broken. The model is
    working, it is simply serialised and someone else has it. Telling a user
    "temporarily unavailable" when the honest answer is "there is a queue"
    invites them to retry immediately, which lengthens the queue.
    """

    service = "llm"
    user_message = (
        "The assistant is busy answering other questions right now. "
        "Please wait a moment and ask again."
    )
