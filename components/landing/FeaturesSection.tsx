import {
  LuActivity,
  LuGauge,
  LuDumbbell,
  LuApple,
  LuMessageSquare,
  LuFlaskConical,
} from "react-icons/lu";
import type { IconType } from "react-icons";
import Container from "@/components/ui/Container";
import SectionHeading from "@/components/ui/SectionHeading";

interface Feature {
  Icon: IconType;
  title: string;
  description: string;
}

const features: Feature[] = [
  {
    Icon: LuActivity,
    title: "Conectado a tu Strava",
    description:
      "Sincroniza automáticamente tus actividades. Conocemos tu FTP, tu fatiga y tu forma actual antes de darte cualquier consejo.",
  },
  {
    Icon: LuGauge,
    title: "Planes que se adaptan a ti",
    description:
      "No hay plantillas. Cada sesión, cada semana, cada bloque se construye sobre tus datos reales: potencia, volumen, consistencia.",
  },
  {
    Icon: LuDumbbell,
    title: "Gimnasio aplicado al ciclismo",
    description:
      "Ejercicios de fuerza, core y movilidad específicos para mejorar en la bici. Nada de rutinas de culturismo.",
  },
  {
    Icon: LuApple,
    title: "Nutrición por volumen de carga",
    description:
      "Los macros cambian cada semana según cuánto entrenas. Días duros, días suaves, cargas, competición — todo calculado.",
  },
  {
    Icon: LuMessageSquare,
    title: "Chat en tiempo real",
    description:
      "Pregunta lo que quieras: una sesión para mañana, qué comer antes de una gran fondo, por qué te duelen las rodillas. Respuesta inmediata.",
  },
  {
    Icon: LuFlaskConical,
    title: "Basado en ciencia",
    description:
      "Periodización polarizada, modelo PMC, zonas de potencia Coggan, protocolos validados. No bro-science.",
  },
];

export default function FeaturesSection() {
  return (
    <section
      id="funcionalidades"
      className="scroll-mt-20 py-24 bg-canvas-soft"
    >
      <Container>
        <SectionHeading title="Todo lo que necesitas para rendir al máximo" />

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-12">
          {features.map((feature) => (
            <div
              key={feature.title}
              className="bg-canvas border border-hairline rounded-lg p-8"
            >
              <feature.Icon
                size={24}
                className="text-ink"
                aria-hidden="true"
              />
              <h3 className="font-medium text-[16px] text-ink mt-4 mb-2">
                {feature.title}
              </h3>
              <p className="text-[14px] leading-[1.5] text-ink-mute">
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </Container>
    </section>
  );
}
