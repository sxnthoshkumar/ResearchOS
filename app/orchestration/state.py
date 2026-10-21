"""
Research Workflow Finite State Machine.
Defines valid execution states and transitions for the autonomous research orchestrator.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Set


class WorkflowState(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    RESEARCHING = "RESEARCHING"
    ANALYZING = "ANALYZING"
    VERIFYING = "VERIFYING"
    RETRYING = "RETRYING"
    GENERATING_REPORT = "GENERATING_REPORT"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Valid state transitions graph
VALID_TRANSITIONS: Dict[WorkflowState, Set[WorkflowState]] = {
    WorkflowState.CREATED: {WorkflowState.PLANNING, WorkflowState.CANCELLED, WorkflowState.FAILED},
    WorkflowState.PLANNING: {WorkflowState.RESEARCHING, WorkflowState.FAILED, WorkflowState.CANCELLED},
    WorkflowState.RESEARCHING: {WorkflowState.ANALYZING, WorkflowState.FAILED, WorkflowState.CANCELLED},
    WorkflowState.ANALYZING: {WorkflowState.VERIFYING, WorkflowState.FAILED, WorkflowState.CANCELLED},
    WorkflowState.VERIFYING: {
        WorkflowState.GENERATING_REPORT,
        WorkflowState.RETRYING,
        WorkflowState.FAILED,
        WorkflowState.CANCELLED,
    },
    WorkflowState.RETRYING: {WorkflowState.RESEARCHING, WorkflowState.FAILED, WorkflowState.CANCELLED},
    WorkflowState.GENERATING_REPORT: {WorkflowState.EVALUATING, WorkflowState.FAILED, WorkflowState.CANCELLED},
    WorkflowState.EVALUATING: {WorkflowState.COMPLETED, WorkflowState.FAILED, WorkflowState.CANCELLED},
    WorkflowState.COMPLETED: set(),
    WorkflowState.FAILED: set(),
    WorkflowState.CANCELLED: set(),
}


class InvalidStateTransitionError(Exception):
    """Raised when an illegal transition is attempted in the orchestrator state machine."""
    pass


def validate_transition(current_state: str | WorkflowState, target_state: str | WorkflowState) -> bool:
    curr = WorkflowState(current_state)
    tgt = WorkflowState(target_state)

    if tgt in VALID_TRANSITIONS.get(curr, set()):
        return True

    raise InvalidStateTransitionError(
        f"Invalid state transition attempted: '{curr.value}' -> '{tgt.value}'"
    )
