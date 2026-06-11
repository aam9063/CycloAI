import Container from "@/components/ui/Container";
import SectionHeading from "@/components/ui/SectionHeading";

const steps = [
  {
    number: "01",
    title: "Crea tu cuenta",
    description:
      "Responde 6 preguntas sobre tu objetivo, disponibilidad y experiencia. El proceso completo toma menos de 3 minutos.",
  },
  {
    number: "02",
    title: "La IA construye tu plan",
    description:
      "Entrenamiento, gimnasio y nutrición basados en tu perfil real y en ciencia del deporte. Sin plantillas genéricas.",
  },
  {
    number: "03",
    title: "Entrena y ajusta",
    description:
      "Pregunta lo que necesites cada semana; tu entrenador está disponible 24/7 y aprende con cada sesión.",
  },
];

export default function HowItWorksSection() {
  return (
    <section
      id="como-funciona"
      className="scroll-mt-20 py-24 bg-canvas-soft"
    >
      <Container>
        <SectionHeading title="Tres pasos para entrenar mejor" />

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-14">
          {steps.map((step) => (
            <div
              key={step.number}
              data-reveal-item
              className="group flex flex-col gap-4 items-center text-center md:items-start md:text-left"
            >
              {/* Step number in bordered square */}
              <span
                className="inline-flex items-center justify-center w-10 h-10 rounded-sm border border-hairline-strong text-[13px] font-medium text-ink-mute motion-safe:transition-colors motion-safe:duration-200 group-hover:border-ink group-hover:text-ink"
                aria-hidden="true"
              >
                {step.number}
              </span>

              <h3 className="text-[18px] font-medium leading-[1.3] text-ink">
                {step.title}
              </h3>
              <p className="text-[14px] leading-[1.55] text-ink-mute">
                {step.description}
              </p>
            </div>
          ))}
        </div>
      </Container>
    </section>
  );
}
