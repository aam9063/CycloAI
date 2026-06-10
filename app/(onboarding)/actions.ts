"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import {
  type OnboardingStepId,
  HOURS_MIDPOINT,
  GYM_DAYS_MAP,
} from "@/lib/onboarding/flow";

export type ActionResult = {
  error: string | null;
  nextStep?: OnboardingStepId;
};

// Whitelist: stepId → DB column name. Client never sends column names.
const COLUMN_MAP: Record<OnboardingStepId, string> = {
  objective: "objective",
  weekly_hours: "weekly_hours",
  gym_days: "gym_days_per_week",
  injuries: "injuries",
  power_meter: "has_power_meter",
  ftp: "ftp_estimated",
  target_event: "target_event",
};

const VALID_OBJECTIVES = new Set([
  "gran_fondo",
  "ftp_improvement",
  "weight_loss",
  "climbing",
  "category_upgrade",
]);

/**
 * Saves a single onboarding answer. Uses a step-id whitelist — never accepts
 * column names from the client. Auth gate on every call.
 */
export async function saveOnboardingAnswer(
  stepId: OnboardingStepId,
  rawValue: unknown
): Promise<ActionResult> {
  // Auth gate — must be first.
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return { error: "No autenticado" };
  }

  // Reject unknown stepId.
  if (!(stepId in COLUMN_MAP)) {
    return { error: "Paso inválido" };
  }

  let dbValue: unknown;
  let extraFields: Record<string, unknown> | undefined;
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
        // Return early without DB write.
        return { error: null, nextStep: "ftp" };
      } else if (choice === "power_yes_no_ftp") {
        dbValue = true;
        nextStep = "target_event";
      } else if (choice === "power_no") {
        dbValue = false;
        nextStep = "target_event";
      } else {
        return { error: "Opción de potenciómetro no válida" };
      }
      break;
    }

    case "ftp": {
      // ADR-2: write BOTH ftp_estimated AND has_power_meter atomically.
      const raw = rawValue === "" ? NaN : Number(rawValue);
      if (!Number.isFinite(raw) || !Number.isInteger(raw) || raw < 80 || raw > 500) {
        return { error: "Introduce un valor entre 80 y 500 vatios." };
      }
      dbValue = raw;
      extraFields = { has_power_meter: true };
      nextStep = "target_event";
      break;
    }

    case "target_event": {
      const trimmed = String(rawValue ?? "").trim();
      // Store "" (empty string) as non-null marker so derivation counts it answered.
      dbValue = trimmed;
      break;
    }

    default:
      return { error: "Paso inválido" };
  }

  const updatePayload: Record<string, unknown> = {
    [COLUMN_MAP[stepId]]: dbValue,
    ...extraFields,
  };

  const { error: dbError } = await supabase
    .from("profiles")
    .update(updatePayload)
    .eq("id", user.id);

  if (dbError) {
    return { error: "No se pudo guardar la respuesta. Intenta de nuevo." };
  }

  return { error: null, nextStep };
}

/**
 * Marks the onboarding as complete and redirects to /chat.
 * Re-fetches the profile server-side to guard against client bugs.
 * redirect() is called OUTSIDE try/catch (NEXT_REDIRECT pattern).
 */
export async function completeOnboarding(): Promise<ActionResult> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return { error: "No autenticado" };
  }

  // Defense: re-fetch and verify all gating fields are answered.
  const { data: profile, error: fetchError } = await supabase
    .from("profiles")
    .select(
      "objective,weekly_hours,gym_days_per_week,injuries,has_power_meter,target_event"
    )
    .eq("id", user.id)
    .single();

  if (fetchError || !profile) {
    return { error: "No se pudo verificar el perfil." };
  }

  const gatingFields: (keyof typeof profile)[] = [
    "objective",
    "weekly_hours",
    "gym_days_per_week",
    "injuries",
    "has_power_meter",
    "target_event",
  ];

  for (const field of gatingFields) {
    if (profile[field] === null || profile[field] === undefined) {
      return { error: "Faltan respuestas" };
    }
  }

  const { error: updateError } = await supabase
    .from("profiles")
    .update({ onboarding_completed: true })
    .eq("id", user.id);

  if (updateError) {
    return { error: "No se pudo completar el registro." };
  }

  // redirect() must be called OUTSIDE try/catch — throws NEXT_REDIRECT internally.
  redirect("/chat");
}
