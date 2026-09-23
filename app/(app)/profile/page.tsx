import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { ApiError, serverGet } from "@/lib/api/server";
import type { Profile } from "@/lib/api/types";
import InitialsAvatar from "@/components/profile/InitialsAvatar";
import ProfileForm from "@/components/profile/ProfileForm";
import StravaConnect from "@/components/profile/StravaConnect";
import AccountSection from "@/components/profile/AccountSection";

export const metadata: Metadata = {
  title: "Tu perfil — CycloAI",
};

export default async function ProfilePage() {
  let profile: Profile;
  try {
    profile = await serverGet<Profile>("/profile");
  } catch (err) {
    // Middleware also guards this route, but an absent/expired session here
    // arrives as a 401 from the backend; it must become the same /login
    // redirect as before, not an unhandled 500.
    if (err instanceof ApiError && err.status === 401) {
      redirect("/login");
    }
    throw err;
  }

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
          <InitialsAvatar name={profile.display_name ?? profile.email} />
          <span className="text-[15px] text-ink-mute">
            {profile.display_name ?? profile.email}
          </span>
        </div>

        <ProfileForm
          initialName={profile.display_name ?? null}
          email={profile.email}
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
          connected={profile.strava_connected}
          connectedAt={profile.strava_connected_at ?? null}
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
