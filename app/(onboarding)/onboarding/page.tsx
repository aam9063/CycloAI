import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import type { Profile } from "@/lib/supabase/types";
import OnboardingChat from "@/components/onboarding/OnboardingChat";

export const metadata: Metadata = {
  title: "CycloAI — Primeros pasos",
  description: "Configura tu perfil de entrenamiento",
};

export default async function OnboardingPage() {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Middleware also guards this route, but defensive check is fine.
  if (!user) {
    redirect("/login");
  }

  const { data: profile } = await supabase
    .from("profiles")
    .select(
      "id,display_name,avatar_url,onboarding_completed,objective,weekly_hours,gym_days_per_week,injuries,has_power_meter,ftp_estimated,target_event,target_event_date"
    )
    .eq("id", user.id)
    .single();

  // Page-level completion guard — redirect before any client hydration.
  if (profile?.onboarding_completed) {
    redirect("/chat");
  }

  return <OnboardingChat initialProfile={profile as Profile} />;
}
