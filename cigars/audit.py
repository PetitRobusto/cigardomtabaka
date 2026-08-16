"""业务命令共享的 Agent 审计上下文。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentContext:
    agent_name: str = ""
    agent_run_id: str = ""
    agent_request_id: str = ""
    command_name: str = ""
    idempotency_key: str = ""

    @classmethod
    def from_mapping(cls, raw=None, *, command_name="", idempotency_key=""):
        raw = raw or {}
        return cls(
            agent_name=str(raw.get("agent_name") or raw.get("name") or "").strip(),
            agent_run_id=str(raw.get("agent_run_id") or raw.get("run_id") or "").strip(),
            agent_request_id=str(raw.get("agent_request_id") or raw.get("request_id") or "").strip(),
            command_name=command_name or str(raw.get("command_name") or "").strip(),
            idempotency_key=idempotency_key or str(raw.get("idempotency_key") or "").strip(),
        )

    def movement_fields(self):
        return {
            "agent_name": self.agent_name,
            "agent_run_id": self.agent_run_id,
            "agent_request_id": self.agent_request_id,
            "command_name": self.command_name,
            "idempotency_key": self.idempotency_key,
        }
