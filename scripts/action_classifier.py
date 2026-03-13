"""Action classification and approval decisions for OpsClaw."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ActionClass(StrEnum):
    INTERNAL_LOG = "internal_log"
    INTERNAL_BRIEF = "internal_brief"
    INTERNAL_QUERY = "internal_query"
    AUTO_DRAFT = "auto_draft"
    TASK_CREATE = "task_create"
    CRM_NOTE = "crm_note"
    EXTERNAL_EMAIL = "external_email"
    EXTERNAL_MESSAGE = "external_message"
    CALENDAR_WRITE = "calendar_write"
    CRM_DEAL_CHANGE = "crm_deal_change"
    FINANCIAL = "financial"


class ApprovalDecision(StrEnum):
    EXECUTE = "execute"
    QUEUE_FOR_APPROVAL = "queue_for_approval"
    BLOCK = "block"


@dataclass
class ApprovalPolicy:
    auto_execute: set[ActionClass] = field(
        default_factory=lambda: {
            ActionClass.INTERNAL_LOG,
            ActionClass.INTERNAL_BRIEF,
            ActionClass.INTERNAL_QUERY,
            ActionClass.AUTO_DRAFT,
            ActionClass.TASK_CREATE,
            ActionClass.CRM_NOTE,
        }
    )
    explicit_approval: set[ActionClass] = field(
        default_factory=lambda: {
            ActionClass.EXTERNAL_EMAIL,
            ActionClass.EXTERNAL_MESSAGE,
            ActionClass.CALENDAR_WRITE,
            ActionClass.CRM_DEAL_CHANGE,
        }
    )
    always_block: set[ActionClass] = field(default_factory=lambda: {ActionClass.FINANCIAL})

    def decision_for(self, action_class: ActionClass) -> ApprovalDecision:
        if action_class in self.always_block:
            return ApprovalDecision.BLOCK
        if action_class in self.explicit_approval:
            return ApprovalDecision.QUEUE_FOR_APPROVAL
        return ApprovalDecision.EXECUTE


def classify_action(action_name: str) -> ActionClass:
    normalized = action_name.strip().lower()

    if any(term in normalized for term in ("pay", "refund", "invoice", "wire", "charge", "purchase")):
        return ActionClass.FINANCIAL
    if "calendar" in normalized and any(term in normalized for term in ("create", "update", "delete", "reschedule")):
        return ActionClass.CALENDAR_WRITE
    if any(term in normalized for term in ("send email", "reply email", "outbound email")):
        return ActionClass.EXTERNAL_EMAIL
    if any(term in normalized for term in ("send message", "slack dm", "whatsapp", "telegram contact")):
        return ActionClass.EXTERNAL_MESSAGE
    if any(term in normalized for term in ("deal stage", "forecast", "pipeline", "opportunity value")):
        return ActionClass.CRM_DEAL_CHANGE
    if "crm" in normalized and any(term in normalized for term in ("note", "log interaction")):
        return ActionClass.CRM_NOTE
    if "task" in normalized and any(term in normalized for term in ("create", "add", "capture")):
        return ActionClass.TASK_CREATE
    if any(term in normalized for term in ("draft", "compose reply", "prepare response")):
        return ActionClass.AUTO_DRAFT
    if any(term in normalized for term in ("brief", "summary", "status update")):
        return ActionClass.INTERNAL_BRIEF
    if any(term in normalized for term in ("fetch", "lookup", "read", "check", "sync status")):
        return ActionClass.INTERNAL_QUERY
    return ActionClass.INTERNAL_LOG
