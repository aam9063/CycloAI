"""Workout generator (P4a): prompt assembly, structured+prose output, gate.

Pipeline: retrieve (injected, never-throw) → prompt (athlete's own zone
system only, I1 stated) → injected model client → validate the RAW payload
with :func:`cycloai.domain.cycling_rules.validate_cycling_payload` BEFORE
parsing into the canonical model (the only genuine I1 enforcement point) →
parse → model-level rule validators → one findings-aware retry → fail closed.

The HTTP endpoint is deliberately NOT part of this package: it will call
:func:`generate_workout` later. The model client and the retrieval callable
are both injected, so tests run with fakes and no network or database.

Product-rule ledger carried over from the live TypeScript chat prompt
(``lib/ai/system-prompt.ts``, read-only reference):

KEPT (still true, still actionable here)
    0. Injection safety over the reference-data blocks.
    1. Ground every recommendation in the athlete's real data; no generic plans.
    2. TSB < -20 → prioritise recovery and warn before proposing intensity
       (enforced again at model level by the plan rule validators when the
       caller supplies CTL/ATL/TSB).
    3. TSB > +15 with high CTL → the athlete tolerates quality work.
    5. Session structure: warm-up, main block, cool-down (now as explicit
       ``role`` values, which the raw gate enforces as errors).
    8 (partial). Unusual fatigue/pain in the request → recovery first.
    10. Plain-text prose: no Markdown in ``prose``/``notes``.

ADAPTED
    7. Nutrition by training volume survives as a note-level guidance rule
       (rule 6 of the generator prompt): the workout schema has no nutrition
       fields, so the product decision lives in the coach's notes.
    The "FTTP/FTP in watts" formatting of the Strava block does NOT survive
    for heart-rate athletes: the threshold line is rendered per declared
    system (FTP in watts, or LTHR in bpm), never both.

DROPPED (with reason)
    4. Previous-week overload warning: it needs a 4-week load history the
       generation request does not carry; the plan-level validator (T8)
       owns load progression when a multi-week plan exists.
    5 (partial). "TSS estimado" is no longer requested from the model: TSS is
       derived by us from the structure (I5) and is power-anchored, so asking
       the model to emit it would assume the superseded model.
    6. Gym-specific plans: this service generates and gates CYCLING workouts
       (the gate is ``validate_cycling_payload``); a gym generator behind
       ``validate_gym_blocks`` is a separate surface, not a silent mix.
    9. "Redirect off-sport topics": chat-conversation behaviour; a one-shot
       generator has no conversation to redirect.
"""

from cycloai.generator.generate import (
    MAX_ATTEMPTS,
    GenerationFinding,
    GenerationResult,
    ModelClient,
    RetrieveFn,
    build_retry_prompt,
    generate_workout,
)
from cycloai.generator.prompt import GenerationRequest, build_workout_prompt

__all__ = [
    "MAX_ATTEMPTS",
    "GenerationFinding",
    "GenerationRequest",
    "GenerationResult",
    "ModelClient",
    "RetrieveFn",
    "build_retry_prompt",
    "build_workout_prompt",
    "generate_workout",
]
