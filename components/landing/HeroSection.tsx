import Button from "@/components/ui/Button";
import Container from "@/components/ui/Container";

function ChatMockup() {
  return (
    <div
      role="img"
      aria-label="Vista previa del chat de CycloAI"
      className="rounded-lg border border-hairline bg-canvas shadow-float overflow-hidden max-w-[440px] w-full"
    >
      {/* Header strip */}
      <div className="bg-canvas-soft border-b border-hairline px-4 py-3 flex items-center gap-2">
        <span className="w-2.5 h-2.5 rounded-full bg-primary" aria-hidden="true" />
        <span className="text-[13px] font-medium text-ink">CycloAI</span>
        <div className="ml-auto flex gap-1.5" aria-hidden="true">
          <span className="w-2.5 h-2.5 rounded-full border border-hairline" />
          <span className="w-2.5 h-2.5 rounded-full border border-hairline" />
          <span className="w-2.5 h-2.5 rounded-full border border-hairline" />
        </div>
      </div>

      {/* Chat body */}
      <div className="px-4 py-5 flex flex-col gap-4">
        {/* User bubble */}
        <div className="flex justify-end">
          <div className="bg-canvas-soft border border-hairline rounded-lg px-3 py-2 text-[14px] text-ink max-w-[220px]">
            ¿Qué entreno hoy?
          </div>
        </div>

        {/* Assistant bubble */}
        <div className="flex justify-start">
          <div className="bg-canvas border border-hairline-cool rounded-lg p-3 text-[14px] text-ink max-w-[300px] flex flex-col gap-3">
            <p className="leading-[1.5]">
              Con tu TSB actual, hoy es perfecto para un bloque de calidad. Te sugiero 75 min zona 3–4.
            </p>
            {/* Metric chip */}
            <div className="border border-hairline rounded-md px-3 py-2 flex gap-3">
              <span className="text-[12px] text-ink-mute">Estado de forma</span>
              <span className="text-[12px] font-medium text-primary-deep ml-auto">
                TSB +4 · CTL 62
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Faux input row */}
      <div className="bg-canvas border-t border-hairline px-4 py-3 flex items-center gap-3">
        <span className="flex-1 text-[13px] text-ink-faint">
          Escribí tu mensaje…
        </span>
        <span
          aria-hidden="true"
          className="w-7 h-7 rounded-full bg-primary flex items-center justify-center"
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M2 6h8M6 2l4 4-4 4"
              stroke="#171717"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </div>
    </div>
  );
}

export default function HeroSection() {
  return (
    <section className="py-16 lg:py-20 bg-canvas">
      <Container>
        <div className="grid md:grid-cols-2 gap-10 lg:gap-16 items-center">
          {/* Left column — text */}
          <div className="flex flex-col gap-6">
            <p className="text-[13px] font-medium text-ink-mute uppercase tracking-wider">
              Entrenamiento inteligente para ciclistas
            </p>
            <h1 className="display-xxl text-ink">
              Tu entrenador personal de ciclismo, potenciado por IA
            </h1>
            <p className="text-[18px] leading-[1.55] text-ink-mute max-w-lg">
              Conecta Strava, responde 6 preguntas y obtén planes de entrenamiento, gimnasio y nutrición adaptados a tu estado de forma real. Sin planes genéricos.
            </p>
            <div className="flex flex-wrap items-center gap-4">
              <Button variant="primary" href="/login">
                Empezar gratis con Strava
              </Button>
              <a
                href="#funcionalidades"
                className="text-[14px] font-medium text-ink-mute hover:text-ink hover:underline underline-offset-4 motion-safe:transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
              >
                Ver cómo funciona
              </a>
            </div>
          </div>

          {/* Right column — chat mockup */}
          <div className="flex justify-center md:justify-end">
            <ChatMockup />
          </div>
        </div>
      </Container>
    </section>
  );
}
