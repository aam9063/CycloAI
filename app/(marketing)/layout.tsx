import type { Metadata } from "next";
import Navbar from "@/components/landing/Navbar";
import Footer from "@/components/landing/Footer";

export const metadata: Metadata = {
  title: "CycloAI — Tu entrenador personal de ciclismo con IA",
  description:
    "Conecta Strava, responde 6 preguntas y obtén planes de entrenamiento, gimnasio y nutrición adaptados a tu estado de forma real. Sin planes genéricos.",
};

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      {/* Skip navigation for keyboard accessibility */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[100] focus:bg-canvas focus:text-ink focus:px-4 focus:py-2 focus:rounded-sm focus:border focus:border-hairline-strong focus:shadow-float"
      >
        Ir al contenido principal
      </a>
      <Navbar />
      <main id="main-content">{children}</main>
      <Footer />
    </>
  );
}
