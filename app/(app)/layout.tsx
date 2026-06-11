import Link from "next/link";
import Image from "next/image";
import NavLinks from "@/components/app/NavLinks";
import UserMenu from "@/components/app/UserMenu";
import { createClient } from "@/lib/supabase/server";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Fetch session + profile display_name server-side.
  // Both can be null (unauthenticated edge or profile not yet created) — handle defensively.
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  let displayName: string | null = null;
  if (user) {
    const { data } = await supabase
      .from("profiles")
      .select("display_name")
      .eq("id", user.id)
      .single();
    displayName = data?.display_name ?? null;
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
