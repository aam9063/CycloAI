import Container from "@/components/ui/Container";
import SectionHeading from "@/components/ui/SectionHeading";

const faqs = [
  {
    question: "¿Necesito un medidor de potencia?",
    answer:
      "No. CycloAI se adapta a cualquier nivel de equipamiento. Si entrenas sin potencia, usamos datos de frecuencia cardíaca, distancia y percepción de esfuerzo. Con potenciómetro, las recomendaciones son más precisas porque trabajamos directamente con vatios y zonas Coggan.",
  },
  {
    question: "¿En qué se diferencia de un plan genérico de internet?",
    answer:
      "Cada respuesta tiene en cuenta tu perfil completo: objetivo actual, horas disponibles, posibles lesiones y FTP estimado. No hay dos atletas iguales ni dos planes iguales. Un plan genérico no sabe que llevas tres semanas de carga alta o que la rodilla derecha te molesta en subidas largas.",
  },
  {
    question: "¿Puedo cancelar cuando quiera?",
    answer:
      "Sí. No hay contratos ni permanencia mínima. Cancelas desde tu perfil en cualquier momento y el acceso se mantiene hasta el final del período facturado.",
  },
  {
    question: "¿Qué métodos de pago se aceptan?",
    answer:
      "Los pagos se procesan de forma segura a través de Stripe y Lemon Squeezy. Puedes pagar con las principales tarjetas de crédito y débito (Visa, Mastercard, American Express), y según tu región, con métodos locales como Apple Pay o Google Pay. CycloAI nunca almacena los datos de tu tarjeta.",
  },
  {
    question: "¿Mis datos están seguros?",
    answer:
      "Sí. Tus datos se almacenan cifrados en servidores de la Unión Europea, nunca se venden a terceros y no se usan para entrenar modelos de IA de terceros. Además, puedes eliminar tu cuenta y todos tus datos en cualquier momento desde tu perfil.",
  },
  {
    question: "¿Funciona sin Strava?",
    answer:
      "Sí. La integración con Strava está en desarrollo y llegará próximamente. Con ella, CycloAI analizará tu carga real, calculará tu FTP y afinará cada plan con tus datos objetivos. Sin ella, funciona igualmente bien usando el perfil que completas en el onboarding.",
  },
];

export default function FaqSection() {
  return (
    <section id="faq" className="scroll-mt-20 py-24 bg-canvas">
      <Container>
        <SectionHeading title="Preguntas frecuentes" />

        <div className="mt-12 mx-auto max-w-2xl">
          {faqs.map((faq, i) => (
            <details
              key={faq.question}
              data-reveal-item
              // Native exclusive accordion: details sharing a name behave like
              // radio buttons — opening one closes the rest. Zero JS.
              name="faq-accordion"
              className={`group border-hairline ${i === 0 ? "border-t" : ""} border-b`}
            >
              <summary
                className="
                  flex items-center justify-between gap-4
                  cursor-pointer select-none list-none
                  py-5 text-[15px] font-medium text-ink
                  hover:text-ink-mute motion-safe:transition-colors
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2
                "
              >
                {faq.question}

                {/* Chevron — rotates 180deg when open, motion-safe gated */}
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  fill="none"
                  aria-hidden="true"
                  className="shrink-0 text-ink-mute motion-safe:transition-transform motion-safe:duration-200 group-open:rotate-180"
                >
                  <path
                    d="M3 6l5 5 5-5"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </summary>

              <p className="pb-5 text-[14px] leading-[1.65] text-ink-mute">
                {faq.answer}
              </p>
            </details>
          ))}
        </div>
      </Container>
    </section>
  );
}
