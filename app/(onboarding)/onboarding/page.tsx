import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { ApiError, serverGet } from "@/lib/api/server";
import type { Profile } from "@/lib/api/types";
import OnboardingChat from "@/components/onboarding/OnboardingChat";

export const metadata: Metadata = {
  title: "CycloAI — Primeros pasos",
  description: "Configura tu perfil de entrenamiento",
};

export default async function OnboardingPage() {
  let profile: Profile | null = null;
  let needsLogin = false;

  try {
    profile = await serverGet<Profile>("/profile");
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      needsLogin = true;
    } else {
      throw err;
    }
  }

  if (needsLogin || profile === null) {
    // redirect() must be called OUTSIDE try/catch — throws NEXT_REDIRECT internally.
    redirect("/login");
  }

  // Page-level completion guard — redirect before any client hydration.
  if (profile.onboarding_completed) {
    redirect("/chat");
  }

  return <OnboardingChat initialProfile={profile} />;
}
