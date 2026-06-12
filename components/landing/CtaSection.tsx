import { LuCheck } from "react-icons/lu";
import Container from "@/components/ui/Container";
import WaitlistForm from "@/components/landing/WaitlistForm";

const reassurances = [
  "Sin spam",
  "Solo te avisaremos del lanzamiento",
  "Baja cuando quieras",
];

export default function CtaSection() {
  return (
    <section id="waitlist" className="scroll-mt-20 py-24 bg-canvas-night">
      <Container className="text-center">
        <p className="text-[13px] font-medium uppercase tracking-wider text-primary mb-4">
          Acceso anticipado
        </p>
        <h2 className="display-lg text-on-dark mb-4 max-w-2xl mx-auto">
          Sé de los primeros en entrenar con CycloAI
        </h2>
        <p className="text-[18px] leading-[1.55] text-on-dark/70 mb-10 max-w-xl mx-auto">
          Estamos abriendo el acceso por orden de lista. Los primeros 100
          inscritos obtienen 3 meses de Premium gratis al lanzamiento.
        </p>

        {/* Waitlist form — centered, constrained width */}
        <div className="mx-auto max-w-md">
          <WaitlistForm source="landing-cta" />
        </div>

        {/* Reassurance row */}
        <ul className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-2">
          {reassurances.map((item) => (
            <li
              key={item}
              className="flex items-center gap-1.5 text-[13px] text-on-dark/60"
            >
              <LuCheck size={14} className="text-primary" aria-hidden="true" />
              {item}
            </li>
          ))}
        </ul>
      </Container>
    </section>
  );
}
