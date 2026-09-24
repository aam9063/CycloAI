"use server";

import { redirect } from "next/navigation";
import { ApiError, serverGet, serverPatch, serverPost } from "@/lib/api/server";
import type { Profile, ProfileUpdate } from "@/lib/api/types";
import {
  type OnboardingStepId,
  HOURS_MIDPOINT,
  GYM_DAYS_MAP,
} from "@/lib/onboarding/flow";

export type ActionResult = {
  error: string | null;
  nextStep?: OnboardingStepId;
};

// Whitelist: stepId → the ProfileUpdate field(s) it may send. The client
// never sends field names, and PATCH /profile rejects unknown fields, so each
// request carries exactly one mapped field — with ONE documented exception:
// the "ftp" step also sends "has_power_meter" because ADR-2 defers the sensor
// flag from the "power_meter" step (power_yes_ftp) to the answer that
// completes the pair. See the "ftp" case below.
const COLUMN_MAP: Record<OnboardingStepId, keyof ProfileUpdate> = {
  objective: "objective",
  weekly_hours: "weekly_hours",
  gym_days: "gym_days_per_week",
  injuries: "injuries",
  power_meter: "has_power_meter",
  ftp: "ftp_estimated",
  training_system: "training_system",
  lthr: "lthr_bpm",
  target_event: "target_event",
};

const VALID_OBJECTIVES = new Set([
  "gran_fondo",
  "ftp_improvement",
  "weight_loss",
  "climbing",
  "category_upgrade",
]);

// Human-readable names for the fields the completion gate can name as missing.
// The backend's 422 says WHICH value is missing; this is what surfaces it.
const MISSING_FIELD_LABELS: Record<string, string> = {
  training_system: "cómo entrenas (potencia o frecuencia cardíaca)",
  lthr_bpm: "tu LTHR (frecuencia cardíaca de umbral)",
  ftp_estimated: "tu FTP",
};

/**
 * Maps a 422 from POST /onboarding/complete to a message naming the missing
 * value(s), so a blocked completion tells the athlete what to answer instead
 * of failing vaguely. Any other shape falls back to the existing message.
 */
function completionGateMessage(err: ApiError): string {
  const detail = err.body?.detail;
  if (typeof detail !== "string") {
    return "No se pudo completar el registro.";
  }
  const match = detail.match(/missing required field\(s\): (.+)/);
  if (!match) {
    return "No se pudo completar el registro.";
  }
  const labels = match[1]
    .replace(/\.$/, "")
    .split(",")
    .map((name) => MISSING_FIELD_LABELS[name.trim()])
    .filter((label): label is string => label !== undefined);
  if (labels.length === 0) {
    return "No se pudo completar el registro.";
  }
  return `Falta por responder: ${labels.join(", ")}.`;
}

/**
 * Saves a single onboarding answer. Uses a step-id whitelist — never accepts
 * field names from the client. Auth is enforced by the backend: a 401 becomes
 * the same redirect to the login page the rest of the app uses.
 */
export async function saveOnboardingAnswer(
  stepId: OnboardingStepId,
  rawValue: unknown
): Promise<ActionResult> {
  // Reject unknown stepId.
  if (!(stepId in COLUMN_MAP)) {
    return { error: "Paso inválido" };
  }

  let dbValue: unknown;
  let nextStep: OnboardingStepId | undefined;

  // Per-step transform + validation.
  switch (stepId) {
    case "objective": {
      if (typeof rawValue !== "string" || !VALID_OBJECTIVES.has(rawValue)) {
        return { error: "Objetivo no válido" };
      }
      dbValue = rawValue;
      break;
    }

    case "weekly_hours": {
      const label = String(rawValue);
      const midpoint = HOURS_MIDPOINT[label];
      if (midpoint === undefined) {
        return { error: "Opción de horas no válida" };
      }
      dbValue = midpoint;
      break;
    }

    case "gym_days": {
      const label = String(rawValue);
      const days = GYM_DAYS_MAP[label];
      if (days === undefined) {
        return { error: "Opción de gimnasio no válida" };
      }
      dbValue = days;
      break;
    }

    case "injuries": {
      const trimmed = String(rawValue ?? "").trim().slice(0, 500);
      // Store "Ninguna" when empty so derivation counts this field as answered.
      dbValue = trimmed.length > 0 ? trimmed : "Ninguna";
      break;
    }

    case "power_meter": {
      const choice = String(rawValue);
      if (choice === "power_yes_ftp") {
        // ADR-2: do NOT persist has_power_meter yet; signal client to show Q5b.
        // Return early without a write.
        return { error: null, nextStep: "ftp" };
      } else if (choice === "power_yes_no_ftp") {
        dbValue = true;
        nextStep = "training_system";
      } else if (choice === "power_no") {
        dbValue = false;
        nextStep = "training_system";
      } else {
        return { error: "Opción de potenciómetro no válida" };
      }
      break;
    }

    case "ftp": {
      // ADR-2 pattern: after the FTP answer, the athlete declares how they train.
      const raw = rawValue === "" ? NaN : Number(rawValue);
      if (!Number.isFinite(raw) || !Number.isInteger(raw) || raw < 80 || raw > 500) {
        return { error: "Introduce un valor entre 80 y 500 vatios." };
      }
      dbValue = raw;
      nextStep = "training_system";
      break;
    }

    case "training_system": {
      const choice = String(rawValue);
      if (choice !== "power" && choice !== "heart_rate") {
        return { error: "Opción de sistema de entrenamiento no válida" };
      }
      dbValue = choice;

      // Branch like power_meter does: the declared system needs its MATCHING
      // threshold before completion (the backend gate refuses otherwise), so
      // route to the conditional threshold step exactly when it is still owed.
      let current: Profile;
      try {
        current = await serverGet<Profile>("/profile");
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          redirect("/login");
        }
        return { error: "No se pudo guardar la respuesta. Intenta de nuevo." };
      }

      if (choice === "power" && current.ftp_estimated === null) {
        nextStep = "ftp";
      } else if (choice === "heart_rate" && current.lthr_bpm === null) {
        nextStep = "lthr";
      } else {
        nextStep = "target_event";
      }
      break;
    }

    case "lthr": {
      // Same shape as the ftp case: integer within a sane physiological range.
      const raw = rawValue === "" ? NaN : Number(rawValue);
      if (!Number.isFinite(raw) || !Number.isInteger(raw) || raw < 100 || raw > 220) {
        return { error: "Introduce un valor entre 100 y 220 ppm." };
      }
      dbValue = raw;
      nextStep = "target_event";
      break;
    }

    case "target_event": {
      // Cap at 200 chars before storing — this value is interpolated into the system prompt.
      const trimmed = String(rawValue ?? "").trim().slice(0, 200);
      // Store "" (empty string) as non-null marker so derivation counts it answered.
      dbValue = trimmed;
      break;
    }

    default:
      return { error: "Paso inválido" };
  }

  // Exactly one mapped field per request — EXCEPT the documented ADR-2
  // deferred pair below. PATCH /profile rejects unknown fields, so both keys
  // must be whitelisted names.
  //
  // ADR-2 EXCEPTION (ftp step): when the athlete chose power_yes_ftp, the
  // power_meter step deliberately did NOT persist has_power_meter, so the
  // client could show the FTP question without a half-written profile. The
  // sensor flag is therefore owed to THIS answer: it must be written
  // atomically together with ftp_estimated, or an athlete who declared a
  // power meter is left with has_power_meter=false and the generator sees a
  // contradiction. Do NOT "fix" this back to a single field.
  const payload: ProfileUpdate =
    stepId === "ftp"
      ? { ftp_estimated: dbValue as number, has_power_meter: true }
      : ({ [COLUMN_MAP[stepId]]: dbValue } as ProfileUpdate);

  try {
    await serverPatch<Profile>("/profile", payload);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      // redirect() throws NEXT_REDIRECT; it is called from this catch body,
      // not inside the guarded block, so it is never swallowed.
      redirect("/login");
    }
    return { error: "No se pudo guardar la respuesta. Intenta de nuevo." };
  }

  return { error: null, nextStep };
}

/**
 * Marks the onboarding as complete through the backend gate and redirects to
 * /chat. The backend re-validates every required field (training_system plus
 * the matching threshold) and its 422 NAMES what is missing — surfaced to the
 * athlete instead of swallowed. redirect() is called OUTSIDE try/catch
 * (NEXT_REDIRECT pattern).
 */
export async function completeOnboarding(): Promise<ActionResult> {
  try {
    await serverPost<Profile>("/onboarding/complete");
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 401) {
        redirect("/login");
      }
      if (err.status === 422) {
        return { error: completionGateMessage(err) };
      }
    }
    return { error: "No se pudo completar el registro." };
  }

  // redirect() must be called OUTSIDE try/catch — throws NEXT_REDIRECT internally.
  redirect("/chat");
}
