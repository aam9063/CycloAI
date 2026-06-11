import Image from "next/image";
import Container from "@/components/ui/Container";
import img1 from "@/public/img/img1.png";

export default function DemoSection() {
  return (
    <section className="py-24 bg-canvas">
      <Container>
        <div className="text-center mb-10">
          <h2 className="display-lg text-ink">Así se ve tu entrenador</h2>
          <p className="mt-3 text-[16px] text-ink-mute">
            Una interfaz de chat limpia, directa y enfocada en tu rendimiento.
          </p>
        </div>

        {/* Browser-frame card */}
        <div className="mx-auto max-w-[960px] rounded-lg border border-hairline shadow-float overflow-hidden">
          {/* Traffic-light strip */}
          <div className="flex items-center gap-1.5 px-4 py-3 bg-canvas-soft border-b border-hairline">
            <span className="w-3 h-3 rounded-full bg-[#ff5f57]" aria-hidden="true" />
            <span className="w-3 h-3 rounded-full bg-[#ffbd2e]" aria-hidden="true" />
            <span className="w-3 h-3 rounded-full bg-[#28c840]" aria-hidden="true" />
            <span className="ml-3 flex-1 bg-canvas border border-hairline rounded-sm text-[12px] text-ink-faint px-3 py-1 text-center max-w-[280px] mx-auto">
              app.cycloai.com/chat
            </span>
          </div>

          {/* Screenshot */}
          <Image
            src={img1}
            alt="Pantalla principal del chat de CycloAI mostrando el asistente de entrenamiento"
            className="block w-full"
            priority={false}
            placeholder="blur"
          />
        </div>
      </Container>
    </section>
  );
}
