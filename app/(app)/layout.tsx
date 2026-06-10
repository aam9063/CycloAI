import Link from "next/link";
import Button from "@/components/ui/Button";
import NavLinks from "@/components/app/NavLinks";
import { signOutAction } from "./actions";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-canvas">
      <header className="border-b border-hairline">
        <div className="mx-auto flex h-16 w-full max-w-[1280px] items-center justify-between px-6 md:px-8">
          <div className="flex items-center gap-8">
            <Link
              href="/"
              className="flex items-center gap-1 text-[16px] font-semibold text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
            >
              Cyclo
              <span className="text-primary">AI</span>
            </Link>
            <NavLinks />
          </div>
          <form action={signOutAction}>
            <Button variant="outline" type="submit">
              Cerrar sesión
            </Button>
          </form>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
