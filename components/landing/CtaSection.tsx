import { LuCheck } from "react-icons/lu";
import Container from "@/components/ui/Container";
import Button from "@/components/ui/Button";

const reassurances = [
  "Sin tarjeta de crédito",
  "Listo en 2 minutos",
  "Cancela cuando quieras",
];

export default function CtaSection() {
  return (
    <section className="py-24 bg-canvas-night">
      <Container className="text-center">
        <p className="text-[13px] font-medium uppercase tracking-wider text-primary mb-4">
          Tu entrenador te espera
        </p>
        <h2 className="display-lg text-on-dark mb-4 max-w-2xl mx-auto">
          Deja de adivinar. Empieza a entrenar con criterio.
        </h2>
        <p className="text-[18px] leading-[1.55] text-on-dark/70 mb-10 max-w-xl mx-auto">
          Crea tu cuenta, responde 6 preguntas y recibe hoy mismo un plan de
          entrenamiento, gimnasio y nutrición hecho para ti. No para el ciclista
          promedio.
        </p>
        <Button variant="primary" href="/register">
          Empezar gratis
        </Button>
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
