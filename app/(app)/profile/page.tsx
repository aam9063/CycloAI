import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import InitialsAvatar from "@/components/profile/InitialsAvatar";
import ProfileForm from "@/components/profile/ProfileForm";
import StravaConnect from "@/components/profile/StravaConnect";
import AccountSection from "@/components/profile/AccountSection";

export const metadata: Metadata = {
  title: "Tu perfil — CycloAI",
};

export default async function ProfilePage() {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Middleware also guards this route, but defensive check is correct.
  if (!user) {
    redirect("/login");
  }

  const { data: profile } = await supabase
    .from("profiles")
    .select(
      "id,display_name,strava_connected,strava_connected_at"
    )
    .eq("id", user.id)
    .single();

  return (
    <div className="mx-auto w-full max-w-[640px] px-6 py-10 flex flex-col gap-6">
      <h1 className="display-md text-ink">Tu perfil</h1>

      {/* Section 1 — Datos personales */}
      <section
        aria-labelledby="section-personal"
        className="bg-canvas border border-hairline rounded-lg p-8 flex flex-col gap-4"
      >
        <h2
          id="section-personal"
          className="text-[18px] font-medium text-ink"
        >
          Datos personales
        </h2>

        <div className="flex items-center gap-4">
          <InitialsAvatar
            name={profile?.display_name ?? user.email ?? null}
          />
          <span className="text-[15px] text-ink-mute">
            {profile?.display_name ?? user.email ?? ""}
          </span>
        </div>

        <ProfileForm
          initialName={profile?.display_name ?? null}
          email={user.email ?? ""}
        />
      </section>

      {/* Section 2 — Conexiones */}
      <section
        aria-labelledby="section-conexiones"
        className="bg-canvas border border-hairline rounded-lg p-8 flex flex-col gap-4"
      >
        <h2
          id="section-conexiones"
          className="text-[18px] font-medium text-ink"
        >
          Conexiones
        </h2>

        <StravaConnect
          connected={profile?.strava_connected ?? false}
          connectedAt={profile?.strava_connected_at ?? null}
        />
      </section>

      {/* Section 3 — Cuenta */}
      <section
        aria-labelledby="section-cuenta"
        className="bg-canvas border border-hairline rounded-lg p-8 flex flex-col gap-4"
      >
        <h2
          id="section-cuenta"
          className="text-[18px] font-medium text-ink"
        >
          Cuenta
        </h2>

        <AccountSection />
      </section>
    </div>
  );
}
