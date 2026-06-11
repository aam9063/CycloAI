import Image from "next/image";
import Link from "next/link";
import Container from "@/components/ui/Container";

const productLinks = [
  { label: "Funcionalidades", href: "#funcionalidades" },
  { label: "Precios", href: "#precios" },
  { label: "Changelog", href: "#" },
];

const legalLinks = [
  { label: "Política de privacidad", href: "/privacidad" },
  { label: "Términos de uso", href: "/terminos" },
  { label: "Contacto", href: "#" },
];

export default function Footer() {
  return (
    <footer className="bg-canvas border-t border-hairline py-16 text-[13px] text-ink-mute">
      <Container>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {/* Brand column */}
          <div className="flex flex-col gap-2">
            <Image
              src="/img/logo.png"
              alt="CycloAI"
              width={48}
              height={48}
              className="h-12 w-12"
            />
            <p>Tu entrenador personal de ciclismo</p>
            <p className="mt-2">© 2026 CycloAI</p>
          </div>

          {/* Product column */}
          <div className="flex flex-col gap-2">
            <p className="font-medium text-ink mb-1">Producto</p>
            {productLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                className="hover:text-ink motion-safe:transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
              >
                {link.label}
              </a>
            ))}
          </div>

          {/* Legal / Soporte column */}
          <div className="flex flex-col gap-2">
            <p className="font-medium text-ink mb-1">Legal / Soporte</p>
            {legalLinks.map((link) =>
              link.href.startsWith("/") ? (
                <Link
                  key={link.label}
                  href={link.href}
                  className="hover:text-ink motion-safe:transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
                >
                  {link.label}
                </Link>
              ) : (
                <a
                  key={link.label}
                  href={link.href}
                  className="hover:text-ink motion-safe:transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
                >
                  {link.label}
                </a>
              )
            )}
          </div>
        </div>
      </Container>
    </footer>
  );
}
