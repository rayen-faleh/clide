"""Tests for workshop-related schemas and payloads."""

from __future__ import annotations

from clide.api.schemas import (
    WorkshopDialoguePayload,
    WorkshopEndedPayload,
    WorkshopPlanPayload,
    WorkshopStartedPayload,
    WorkshopStepUpdatePayload,
    WSMessageType,
)


class TestWorkshopPayloads:
    """Tests for workshop payload models."""

    def test_workshop_started_payload(self) -> None:
        payload = WorkshopStartedPayload(
            session_id="sess1",
            goal_description="Test goal",
        )
        assert payload.session_id == "sess1"
        assert payload.goal_description == "Test goal"

    def test_workshop_plan_payload(self) -> None:
        payload = WorkshopPlanPayload(
            session_id="sess1",
            objective="Test objective",
            approach="Test approach",
            steps=[
                {
                    "id": "s1",
                    "description": "Step 1",
                    "tools_needed": ["t1"],
                    "status": "pending",
                }
            ],
        )
        assert payload.objective == "Test objective"
        assert len(payload.steps) == 1

    def test_workshop_dialogue_payload(self) -> None:
        payload = WorkshopDialoguePayload(
            session_id="sess1",
            content="Thinking about this...",
        )
        assert payload.content == "Thinking about this..."
        assert payload.is_tool_event is False

    def test_workshop_dialogue_payload_tool_event(self) -> None:
        payload = WorkshopDialoguePayload(
            session_id="sess1",
            content="Used web_search",
            is_tool_event=True,
        )
        assert payload.is_tool_event is True

    def test_workshop_step_update_payload(self) -> None:
        payload = WorkshopStepUpdatePayload(
            session_id="sess1",
            step_index=0,
            status="completed",
            result_summary="Done",
        )
        assert payload.step_index == 0
        assert payload.status == "completed"

    def test_workshop_step_update_payload_defaults(self) -> None:
        payload = WorkshopStepUpdatePayload(
            session_id="sess1",
            step_index=1,
            status="in_progress",
        )
        assert payload.result_summary == ""

    def test_workshop_ended_payload(self) -> None:
        payload = WorkshopEndedPayload(
            session_id="sess1",
            status="completed",
            summary="All done",
        )
        assert payload.status == "completed"
        assert payload.summary == "All done"

    def test_workshop_ended_payload_defaults(self) -> None:
        payload = WorkshopEndedPayload(
            session_id="sess1",
            status="abandoned",
        )
        assert payload.summary == ""

    def test_json_round_trip_started(self) -> None:
        payload = WorkshopStartedPayload(
            session_id="s1",
            goal_description="Test",
        )
        restored = WorkshopStartedPayload.model_validate_json(payload.model_dump_json())
        assert restored == payload

    def test_json_round_trip_plan(self) -> None:
        payload = WorkshopPlanPayload(
            session_id="s1",
            objective="obj",
            approach="app",
            steps=[{"id": "s1", "description": "d"}],
        )
        restored = WorkshopPlanPayload.model_validate_json(payload.model_dump_json())
        assert restored == payload

    def test_json_round_trip_ended(self) -> None:
        payload = WorkshopEndedPayload(
            session_id="s1",
            status="completed",
            summary="done",
        )
        restored = WorkshopEndedPayload.model_validate_json(payload.model_dump_json())
        assert restored == payload


class TestWorkshopMessageTypes:
    """Tests for workshop message type enum values."""

    def test_workshop_started_type(self) -> None:
        assert WSMessageType.WORKSHOP_STARTED.value == "workshop_started"

    def test_workshop_plan_type(self) -> None:
        assert WSMessageType.WORKSHOP_PLAN.value == "workshop_plan"

    def test_workshop_dialogue_type(self) -> None:
        assert WSMessageType.WORKSHOP_DIALOGUE.value == "workshop_dialogue"

    def test_workshop_step_update_type(self) -> None:
        assert WSMessageType.WORKSHOP_STEP_UPDATE.value == "workshop_step_update"

    def test_workshop_ended_type(self) -> None:
        assert WSMessageType.WORKSHOP_ENDED.value == "workshop_ended"
