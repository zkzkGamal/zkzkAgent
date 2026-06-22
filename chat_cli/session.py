"""Chat session state — binds the conversation to a (dummy) user + session."""

import uuid
from datetime import datetime


class ChatSession:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.session_id = uuid.uuid4().hex[:12]
        self.started_at = datetime.now()
        self.turns = 0
        self.state = self.fresh_state()

    @staticmethod
    def fresh_state() -> dict:
        return {
            "messages": [],
            "pending_confirmation": {"tool_name": None, "user_message": None},
            "running_processes": {},
            "category": None,
            "iteration_count": 0,
        }

    def reset(self) -> None:
        self.session_id = uuid.uuid4().hex[:12]
        self.started_at = datetime.now()
        self.turns = 0
        self.state = self.fresh_state()

    @property
    def awaiting_confirmation(self) -> bool:
        pending = self.state.get("pending_confirmation") or {}
        return bool(pending.get("tool_name"))
