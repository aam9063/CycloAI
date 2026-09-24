import Link from "next/link";
import Image from "next/image";
import { redirect } from "next/navigation";
import NavLinks from "@/components/app/NavLinks";
import UserMenu from "@/components/app/UserMenu";
import { ApiError, serverGet } from "@/lib/api/server";
import type { Profile } from "@/lib/api/types";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // The backend validates the session on every request, so the profile read IS
  // the session authority here — no separate auth check. A 401 (expired/absent
  // API session) is a signed-out visitor: login redirect, same as every other
  // screen behind auth. The app shell must not render for a visitor.
  let displayName: string | null = null;
  try {
    const profile = await serverGet<Profile>("/profile");
    displayName = profile.display_name;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      redirect("/login");
    }
    // 404: a valid session whose profile row does not exist (the backend
    // creates rows via trigger, so this is an integrity anomaly, not a normal
    // state). The old auth path degraded gracefully here — render the shell
    // with no name. The two statuses are distinct on the endpoint on purpose:
    // only a 401 means signed-out. Everything else is a real failure.
    if (!(err instanceof ApiError && err.status === 404)) {
      throw err;
    }
  }

  return (
    <div className="min-h-screen bg-canvas">
      <header className="border-b border-hairline">
        <div className="mx-auto flex h-16 w-full max-w-[1280px] items-center justify-between px-6 md:px-8">
          <div className="flex items-center gap-8">
            <Link
              href="/"
              className="flex items-center rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
              aria-label="CycloAI"
            >
              <Image
                src="/img/logo.png"
                alt="CycloAI"
                width={48}
                height={48}
                priority
                className="h-12 w-12"
              />
            </Link>
            <NavLinks />
          </div>
          <UserMenu displayName={displayName} />
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
