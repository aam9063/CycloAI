"""The ``POST /generate`` route: validate → bind → load → generate → map.

Outcome mapping is deliberately honest — the caller must be able to tell the
three outcomes apart without reading server logs:

* **success** → ``200`` with the structured workout, the coach prose, and
  whether knowledge was used (retrieval being empty or failing is still a
  success, with ``knowledge_used: false`` — never an error);
* **the gate exhausted its retry** → ``422`` carrying the findings verbatim,
  each with its ``source`` (``model_response`` / ``raw_payload`` /
  ``model_rules``), because "unusable JSON", "fabricated citation" and "broke
  a plan rule" are three different diagnoses;
* **unexpected failure** → a generic ``500`` (or ``503`` for a missing model
  configuration): no exception text, no stub identity, no credential ever
  reaches a response body.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from cycloai.api.deps import get_current_athlete, get_model_client, get_retrieve, get_session
from cycloai.db.repositories import ProfileRepository, bind_session_user
from cycloai.domain.zones import AthleteThresholds, TrainingSystem
from cycloai.generator.generate import ModelClient, RetrieveFn, generate_workout
from cycloai.generator.prompt import GenerationRequest

__all__ = ["router"]

logger = logging.getLogger("cycloai.api")

router = APIRouter(tags=["generation"])


class ThresholdsIn(BaseModel):
    """The athlete's declared training system and its threshold.

    Mirrors :class:`~cycloai.domain.zones.AthleteThresholds`: the declared
    system's own metric is required and must be positive — a power athlete
    without FTP and a heart-rate athlete without LTHR are refused here, the
    same refusal the domain makes at construction.
    """

    system: Literal["power", "heart_rate"]
    ftp_watts: float | None = Field(default=None, gt=0)
    lthr_bpm: float | None = Field(default=None, gt=0)

    @field_validator("ftp_watts", "lthr_bpm")
    @classmethod
    def _finite(cls, value: float | None) -> float | None:
        if value is not None and (value != value or value in (float("inf"), float("-inf"))):
            raise ValueError("must be a finite number")
        return value

    def to_domain(self) -> AthleteThresholds:
        """Build the frozen domain value object from the validated body."""
        return AthleteThresholds(
            system=TrainingSystem(self.system),
            ftp_watts=self.ftp_watts,
            lthr_bpm=self.lthr_bpm,
        )


class GenerateRequestBody(BaseModel):
    """The real request shape of ``POST /generate``.

    ``objective`` and ``thresholds`` are required (a generation ask without an
    objective, or without the athlete's declared anchor, is not answerable);
    every other field is optional and falls back to the athlete's stored
    profile when omitted, with explicit body values winning.
    """

    objective: str = Field(min_length=1, max_length=2000)
    thresholds: ThresholdsIn
    weekly_hours: float | None = Field(default=None, gt=0, le=100)
    gym_days_per_week: int | None = Field(default=None, ge=0, le=7)
    injuries: str | None = Field(default=None, max_length=2000)
    target_event: str | None = Field(default=None, max_length=500)
    has_power_meter: bool | None = None
    guidance: str | None = Field(default=None, max_length=4000)
    ctl: float | None = None
    atl: float | None = None
    tsb: float | None = None

    @field_validator("objective", "injuries", "target_event", "guidance")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    def to_generation_request(self, profile: Any) -> GenerationRequest:
        """Merge the validated body with the athlete's stored profile.

        The body wins on every field it supplies; profile values fill the
        gaps. A missing profile (``None``) simply means no fallbacks — the
        body already carries everything required.
        """

        def pick(body_value: Any, profile_value: Any) -> Any:
            return body_value if body_value is not None else profile_value

        return GenerationRequest(
            objective=self.objective,
            thresholds=self.thresholds.to_domain(),
            weekly_hours=pick(self.weekly_hours, getattr(profile, "weekly_hours", None)),
            gym_days_per_week=pick(
                self.gym_days_per_week, getattr(profile, "gym_days_per_week", None)
            ),
            injuries=pick(self.injuries, getattr(profile, "injuries", None)),
            target_event=pick(self.target_event, getattr(profile, "target_event", None)),
            has_power_meter=pick(
                self.has_power_meter, getattr(profile, "has_power_meter", False)
            ),
            guidance=self.guidance,
            ctl=pick(self.ctl, getattr(profile, "ctl", None)),
            atl=pick(self.atl, getattr(profile, "atl", None)),
            tsb=pick(self.tsb, getattr(profile, "tsb", None)),
        )


class GenerationFindingOut(BaseModel):
    """One gate finding, verbatim, with the layer it came from."""

    source: str
    code: str
    severity: str
    message: str


class GenerationRejectedOut(BaseModel):
    """The 422 body: the gate refused the model output on every attempt."""

    findings: list[GenerationFindingOut]
    attempts: int


class GenerationSuccessOut(BaseModel):
    """The 200 body: the validated workout plus the coach prose."""

    workout: dict[str, Any]
    prose: str
    knowledge_used: bool


class ErrorOut(BaseModel):
    """A generic error body: never exception text, never internal detail."""

    detail: str


def _findings_out(findings: Any) -> list[GenerationFindingOut]:
    return [
        GenerationFindingOut(
            source=finding.source,
            code=finding.code,
            severity=finding.severity,
            message=finding.message,
        )
        for finding in findings
    ]


@router.post(
    "/generate",
    response_model=GenerationSuccessOut,
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": GenerationRejectedOut,
            "description": (
                "The validation gate rejected the model output on the initial "
                "attempt and on the retry; no plan is returned."
            ),
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorOut,
            "description": "Workout generation is not configured on the server.",
        },
    },
    summary="Generate one validated cycling workout with coach prose.",
)
async def generate(
    body: GenerateRequestBody,
    athlete_id: uuid.UUID = Depends(get_current_athlete),
    session: AsyncSession = Depends(get_session),
    model_client: ModelClient = Depends(get_model_client),
    retrieve: RetrieveFn = Depends(get_retrieve),
) -> Any:
    """Generate one workout for the authenticated athlete.

    The athlete identity comes from the auth seam and is bound onto the
    session BEFORE any repository access; it is never taken from the request
    body. The profile is loaded through the repository layer so the ownership
    guard (fail-closed, unbound-session-refusing) is exercised on every
    request rather than bypassed.
    """
    # Binding uses ONLY the seam's identity. Binding a body-provided id would
    # defeat the repository guard: a user_id you were handed is not
    # authentication.
    bind_session_user(session, athlete_id)

    try:
        profile = await ProfileRepository().get_profile(session, athlete_id)
    except Exception:  # noqa: BLE001 - never leak storage errors to callers
        logger.exception("profile load failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The request could not be completed.",
        ) from None

    request = body.to_generation_request(profile)

    try:
        result = await generate_workout(
            request, model_client=model_client, retrieve=retrieve, log=logger.info
        )
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - never leak pipeline errors to callers
        logger.exception("workout generation failed unexpectedly")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The request could not be completed.",
        ) from None

    if not result.ok or result.workout is None:
        rejected = GenerationRejectedOut(
            findings=_findings_out(result.findings), attempts=result.attempts
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=rejected.model_dump(),
        )

    return GenerationSuccessOut(
        workout=result.workout.model_dump(mode="json"),
        prose=result.prose or "",
        knowledge_used=result.knowledge_used,
    )
