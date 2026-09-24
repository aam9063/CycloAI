// Pure logic module — no React, shared by client and server.
// All question copy is verbatim from CLAUDE.md ONBOARDING_FLOW.

import type { Profile } from "@/lib/api/types";

export type OnboardingStepId =
  | "objective"
  | "weekly_hours"
  | "gym_days"
  | "injuries"
  | "power_meter"
  | "ftp"
  | "training_system"
  | "lthr"
  | "target_event";

export interface OptionDef {
  value: string;
  label: string;
}

export interface StepDef {
  id: OnboardingStepId;
  question: string;
  kind: "options" | "free_text" | "ftp" | "lthr";
  options?: OptionDef[];
  placeholder?: string;
  /** The Profile column that indicates this step is answered (non-null). */
  mapsTo: keyof Profile;
}

// Midpoint map for weekly_hours range labels → numeric value stored in DB.
export const HOURS_MIDPOINT: Record<string, number> = {
  "4-6h": 5.0,
  "6-8h": 7.0,
  "8-10h": 9.0,
  "10-12h": 11.0,
  "Más de 12h": 13.0,
};

// Reverse map: stored midpoint → display label.
const HOURS_REVERSE: Record<number, string> = {
  5: "4-6h",
  7: "6-8h",
  9: "8-10h",
  11: "10-12h",
  13: "Más de 12h",
};

// Gym days: label → DB integer.
export const GYM_DAYS_MAP: Record<string, number> = {
  "No tengo acceso a gimnasio": 0,
  "1 día": 1,
  "2 días": 2,
  "3 días": 3,
};

const GYM_DAYS_REVERSE: Record<number, string> = {
  0: "No tengo acceso a gimnasio",
  1: "1 día",
  2: "2 días",
  3: "3 días",
};

// The 7 main steps (Q5b 'ftp' and the LTHR step are not separate dots —
// both inserted conditionally in session).
export const STEPS: StepDef[] = [
  {
    id: "objective",
    question:
      "¡Hola! Soy CycloAI, tu entrenador personal de ciclismo. Para empezar, ¿cuál es tu principal objetivo ahora mismo?",
    kind: "options",
    options: [
      {
        value: "gran_fondo",
        label: "Prepararme para una gran fondo o cicloturista",
      },
      { value: "ftp_improvement", label: "Mejorar mi FTP y potencia general" },
      {
        value: "weight_loss",
        label: "Perder peso sin perder rendimiento",
      },
      { value: "climbing", label: "Mejorar en subidas (W/kg)" },
      { value: "category_upgrade", label: "Subir de categoría amateur" },
    ],
    mapsTo: "objective",
  },
  {
    id: "weekly_hours",
    question:
      "¿Cuántas horas a la semana puedes dedicar a entrenar? (bici + gimnasio en total)",
    kind: "options",
    options: [
      { value: "4-6h", label: "4-6h" },
      { value: "6-8h", label: "6-8h" },
      { value: "8-10h", label: "8-10h" },
      { value: "10-12h", label: "10-12h" },
      { value: "Más de 12h", label: "Más de 12h" },
    ],
    mapsTo: "weekly_hours",
  },
  {
    id: "gym_days",
    question:
      "¿Tienes acceso a gimnasio? ¿Cuántos días a la semana podrías ir?",
    kind: "options",
    options: [
      { value: "No tengo acceso a gimnasio", label: "No tengo acceso a gimnasio" },
      { value: "1 día", label: "1 día" },
      { value: "2 días", label: "2 días" },
      { value: "3 días", label: "3 días" },
    ],
    mapsTo: "gym_days_per_week",
  },
  {
    id: "injuries",
    question:
      "¿Tienes alguna lesión actual, zona de dolor recurrente, o algo que debamos tener en cuenta?",
    kind: "free_text",
    placeholder: "Ej: Rodilla derecha, lumbar, ninguna...",
    mapsTo: "injuries",
  },
  {
    id: "power_meter",
    question:
      "¿Entrenas con medidor de potencia? Si es así, ¿sabes tu FTP aproximado?",
    kind: "options",
    options: [
      {
        value: "power_yes_ftp",
        label: "Sí, tengo potenciómetro y sé mi FTP",
      },
      {
        value: "power_yes_no_ftp",
        label: "Sí, tengo potenciómetro pero no sé mi FTP",
      },
      { value: "power_no", label: "No tengo potenciómetro" },
    ],
    mapsTo: "has_power_meter",
  },
  {
    id: "training_system",
    question:
      "¿Prefieres guiarte por la potencia o por la frecuencia cardíaca para entrenar?",
    kind: "options",
    options: [
      {
        value: "power",
        label: "Por potencia (zonas a partir de mi FTP)",
      },
      {
        value: "heart_rate",
        label: "Por frecuencia cardíaca (zonas a partir de mi LTHR)",
      },
    ],
    mapsTo: "training_system",
  },
  {
    id: "target_event",
    question:
      "¿Tienes algún evento o carrera objetivo en los próximos meses? (Si no tienes, no pasa nada)",
    kind: "free_text",
    placeholder: "Ej: La Quebrantahuesos en julio, L'Étape en agosto...",
    mapsTo: "target_event",
  },
];

/**
 * Q5b step definition (inserted conditionally — not a separate progress dot).
 */
export const FTP_STEP: StepDef = {
  id: "ftp",
  question: "¿Cuál es tu FTP actual? (en vatios)",
  kind: "ftp",
  mapsTo: "ftp_estimated",
};

/**
 * LTHR step definition (inserted conditionally — not a separate progress dot).
 * Mirrors FTP_STEP: asked only when the athlete's declared training system
 * needs it (heart_rate), exactly as Q5b is asked only when a power-meter
 * athlete still owes an FTP.
 */
export const LTHR_STEP: StepDef = {
  id: "lthr",
  question: "¿Cuál es tu LTHR? (frecuencia cardíaca de umbral, en ppm)",
  kind: "lthr",
  mapsTo: "lthr_bpm",
};

/**
 * Returns the index into STEPS of the first unanswered step, or -1 if all answered.
 * Derivation order: objective → weekly_hours → gym_days_per_week → injuries →
 * has_power_meter → training_system → target_event.
 * Note: ftp (Q5b) and lthr are NOT gating columns here — both are handled
 * in-session via the power_meter / training_system branches (ADR-2 pattern).
 * has_power_meter null means power_meter is unanswered.
 */
export function firstUnansweredStep(profile: Profile): number {
  for (let i = 0; i < STEPS.length; i++) {
    const step = STEPS[i];
    const value = profile[step.mapsTo];
    if (value === null || value === undefined) {
      return i;
    }
  }
  return -1;
}

/**
 * Returns the human-readable answer label for a given step and stored DB value.
 * Used when replaying answered steps as history bubbles.
 */
export function labelForAnswer(
  stepId: OnboardingStepId,
  profileValue: unknown
): string {
  switch (stepId) {
    case "objective": {
      const step = STEPS.find((s) => s.id === "objective");
      const option = step?.options?.find((o) => o.value === profileValue);
      return option?.label ?? String(profileValue);
    }
    case "weekly_hours": {
      const num = typeof profileValue === "number" ? profileValue : Number(profileValue);
      return HOURS_REVERSE[num] ?? String(profileValue);
    }
    case "gym_days": {
      const num = typeof profileValue === "number" ? profileValue : Number(profileValue);
      return GYM_DAYS_REVERSE[num] ?? String(profileValue);
    }
    case "injuries": {
      if (
        profileValue === null ||
        profileValue === undefined ||
        profileValue === ""
      )
        return "Ninguna";
      return String(profileValue);
    }
    case "power_meter": {
      // has_power_meter is boolean; map back to a display string.
      // We cannot distinguish which option was chosen, so use generic label.
      if (profileValue === true) return "Sí, tengo potenciómetro";
      if (profileValue === false) return "No tengo potenciómetro";
      return String(profileValue);
    }
    case "ftp": {
      return `${profileValue} W`;
    }
    case "training_system": {
      const step = STEPS.find((s) => s.id === "training_system");
      const option = step?.options?.find((o) => o.value === profileValue);
      return option?.label ?? String(profileValue);
    }
    case "lthr": {
      return `${profileValue} ppm`;
    }
    case "target_event": {
      if (
        profileValue === null ||
        profileValue === undefined ||
        profileValue === ""
      )
        return "Sin evento objetivo";
      return String(profileValue);
    }
    default:
      return String(profileValue);
  }
}
