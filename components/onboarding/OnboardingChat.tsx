"use client";

import {
  useEffect,
  useRef,
  useState,
  useTransition,
  useCallback,
} from "react";
import type { Profile } from "@/lib/supabase/types";
import {
  STEPS,
  FTP_STEP,
  firstUnansweredStep,
  labelForAnswer,
  type OnboardingStepId,
  type StepDef,
} from "@/lib/onboarding/flow";
import {
  saveOnboardingAnswer,
  completeOnboarding,
} from "@/app/(onboarding)/actions";
import QuestionBubble from "./QuestionBubble";
import UserBubble from "./UserBubble";
import ProgressDots from "./ProgressDots";
import OptionGroup from "./OptionGroup";
import FreeTextAnswer from "./FreeTextAnswer";
import FtpInput from "./FtpInput";

interface LogEntry {
  type: "question" | "answer";
  content: string;
  key: string;
}

interface OnboardingChatProps {
  initialProfile: Profile;
}

export default function OnboardingChat({ initialProfile }: OnboardingChatProps) {
  // ── Derive initial state from the persisted profile ──────────────────────
  const firstUnanswered = firstUnansweredStep(initialProfile);

  // Build static history of already-answered Q&A pairs.
  function buildHistory(profile: Profile): LogEntry[] {
    const history: LogEntry[] = [];
    const unanswered = firstUnansweredStep(profile);
    const limit = unanswered === -1 ? STEPS.length : unanswered;

    for (let i = 0; i < limit; i++) {
      const step = STEPS[i];
      history.push({
        type: "question",
        content: step.question,
        key: `q-history-${step.id}`,
      });
      const rawValue = profile[step.mapsTo];
      history.push({
        type: "answer",
        content: labelForAnswer(step.id, rawValue),
        key: `a-history-${step.id}`,
      });
    }
    return history;
  }

  const initialHistory = buildHistory(initialProfile);
  const initialStep =
    firstUnanswered === -1 ? null : STEPS[firstUnanswered];

  // Add the first question bubble to the log if there's a step to show.
  const initialLog: LogEntry[] = initialStep
    ? [
        ...initialHistory,
        {
          type: "question",
          content: initialStep.question,
          key: `q-live-${initialStep.id}`,
        },
      ]
    : initialHistory;

  // ── State ─────────────────────────────────────────────────────────────────
  const [log, setLog] = useState<LogEntry[]>(initialLog);
  const [currentStep, setCurrentStep] = useState<StepDef | null>(initialStep);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  // True only after the user answers a question — suppresses focus steal on initial render.
  const [isTransition, setIsTransition] = useState(false);

  // Scroll anchor — bottom of the chat log.
  const bottomRef = useRef<HTMLDivElement>(null);

  // ── Auto-scroll when log changes (always instant per spec §1.11) ──────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "instant" });
  }, [log]);

  // ── Complete flow on mount if all fields already answered ─────────────
  useEffect(() => {
    if (firstUnanswered === -1) {
      startTransition(async () => {
        await completeOnboarding();
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Answer handler ────────────────────────────────────────────────────
  const handleAnswer = useCallback(
    (stepId: OnboardingStepId, rawValue: unknown) => {
      // Find the display label for the user bubble.
      const step = STEPS.find((s) => s.id === stepId) ?? (stepId === "ftp" ? FTP_STEP : null);
      const displayLabel =
        stepId === "ftp"
          ? `${rawValue} W`
          : step?.kind === "options"
          ? (step.options?.find((o) => o.value === rawValue)?.label ?? String(rawValue))
          : String(rawValue ?? "");

      setError(null);

      startTransition(async () => {
        const result = await saveOnboardingAnswer(stepId, rawValue);

        if (result.error) {
          setError(result.error);
          return;
        }

        // Append user answer bubble.
        const answerKey = `a-live-${stepId}-${Date.now()}`;
        setLog((prev) => [
          ...prev,
          { type: "answer", content: displayLabel, key: answerKey },
        ]);

        // Determine next step.
        const nextStepId = result.nextStep;

        if (nextStepId === "ftp") {
          // Q5b branch: show FTP question without adding a new dot.
          setIsTransition(true);
          setCurrentStep(FTP_STEP);
          setLog((prev) => [
            ...prev,
            {
              type: "question",
              content: FTP_STEP.question,
              key: `q-live-ftp-${Date.now()}`,
            },
          ]);
          return;
        }

        // Find the next main step.
        let nextMainStep: StepDef | null = null;

        if (nextStepId) {
          // Server told us which step is next (e.g. power_meter branches).
          nextMainStep = STEPS.find((s) => s.id === nextStepId) ?? null;
        } else {
          // Normal sequential advance.
          const currentIndex = STEPS.findIndex((s) => s.id === stepId);
          if (currentIndex !== -1 && currentIndex + 1 < STEPS.length) {
            nextMainStep = STEPS[currentIndex + 1];
          }
        }

        if (nextMainStep) {
          setIsTransition(true);
          setCurrentStep(nextMainStep);
          setLog((prev) => [
            ...prev,
            {
              type: "question",
              content: nextMainStep!.question,
              key: `q-live-${nextMainStep!.id}-${Date.now()}`,
            },
          ]);
        } else {
          // All questions answered — complete.
          setCurrentStep(null);
          await completeOnboarding();
        }
      });
    },
    []
  );

  // ── Current step index for progress dots ─────────────────────────────
  const currentStepIndex = currentStep
    ? STEPS.findIndex((s) => s.id === currentStep.id)
    : -1;
  // Answered count: how many main STEPS are before the current one.
  const answeredCount =
    currentStepIndex === -1 ? STEPS.length : currentStepIndex;

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div className="mx-auto w-full max-w-[480px] px-6 py-8 flex flex-col gap-4">
      {/* Hidden h1 for screen readers — logo is visual; one h1 per page (spec §1.10) */}
      <h1 className="sr-only">CycloAI — Primeros pasos</h1>

      <ProgressDots
        total={STEPS.length}
        answeredCount={answeredCount}
        currentIndex={currentStepIndex === -1 ? STEPS.length - 1 : currentStepIndex}
      />

      {/* Scrollable chat log with aria-live region for new bubbles */}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="flex flex-col gap-3 min-h-0"
      >
        {log.map((entry) =>
          entry.type === "question" ? (
            <QuestionBubble key={entry.key}>{entry.content}</QuestionBubble>
          ) : (
            <UserBubble key={entry.key}>{entry.content}</UserBubble>
          )
        )}

        {/* Scroll anchor */}
        <div ref={bottomRef} />
      </div>

      {/* Persistence error banner */}
      {error && (
        <p
          role="alert"
          aria-live="assertive"
          className="text-[13px] text-ink-mute leading-[1.45] px-1"
        >
          {error}
        </p>
      )}

      {/* Current step controls */}
      {currentStep && (
        <div className="mt-2">
          {currentStep.kind === "options" && currentStep.options && (
            <OptionGroup
              key={currentStep.id}
              options={currentStep.options}
              onSelect={(value) => handleAnswer(currentStep.id, value)}
              disabled={isPending}
              name={currentStep.question}
              shouldFocus={isTransition}
            />
          )}

          {currentStep.kind === "free_text" && (
            <FreeTextAnswer
              key={currentStep.id}
              id={`free-text-${currentStep.id}`}
              label={currentStep.question}
              placeholder={currentStep.placeholder}
              maxLength={currentStep.id === "injuries" ? 500 : undefined}
              showCounter={currentStep.id === "injuries"}
              multiline={currentStep.id === "injuries"}
              onSubmit={(value) => handleAnswer(currentStep.id, value)}
              disabled={isPending}
              shouldFocus={isTransition}
            />
          )}

          {currentStep.kind === "ftp" && (
            <FtpInput
              key="ftp"
              onSubmit={(watts) => handleAnswer("ftp", watts)}
              disabled={isPending}
              error={error}
              shouldFocus={isTransition}
            />
          )}
        </div>
      )}

      {/* Loading state for screen readers */}
      {isPending && (
        <p aria-live="polite" className="sr-only">
          Guardando respuesta...
        </p>
      )}
    </div>
  );
}
