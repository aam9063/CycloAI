import Button from "@/components/ui/Button";
import Container from "@/components/ui/Container";
import Iphone from "@/components/ui/Iphone";
import HeroIntro from "@/components/landing/HeroIntro";

export default function HeroSection() {
  return (
    <section className="py-16 lg:py-20 bg-canvas overflow-hidden">
      <Container>
        {/*
          HeroIntro is a 'use client' wrapper. Its children (this JSX tree) are
          still server-rendered — client components can receive RSC children.
          It adds data-attribute-driven stagger on load via useGSAP.
        */}
        <HeroIntro className="grid md:grid-cols-2 gap-10 lg:gap-16 items-center">
          {/* Left column — text. Centered on mobile, left-aligned from md up. */}
          <div className="flex flex-col gap-6 items-center text-center md:items-start md:text-left">
            <p
              data-hero-item
              className="text-[13px] font-medium text-ink-mute uppercase tracking-wider"
            >
              Entrenamiento inteligente para ciclistas
            </p>
            <h1 data-hero-item className="display-xxl text-ink">
              Tu entrenador personal de ciclismo, potenciado por IA
            </h1>
            <p
              data-hero-item
              className="text-[18px] leading-[1.55] text-ink-mute max-w-lg"
            >
              Conecta Strava, responde 6 preguntas y obtén planes de
              entrenamiento, gimnasio y nutrición adaptados a tu estado de forma
              real. Sin planes genéricos.
            </p>
            <div data-hero-item className="flex flex-col items-center md:items-start gap-3">
              <div className="flex flex-wrap items-center justify-center md:justify-start gap-4">
                <Button variant="primary" href="#waitlist">
                  Unirme a la lista de espera
                </Button>
                <a
                  href="#como-funciona"
                  className="text-[14px] font-medium text-ink-mute hover:text-ink hover:underline underline-offset-4 motion-safe:transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
                >
                  Ver cómo funciona
                </a>
              </div>
              <p className="text-[13px] text-ink-mute">
                Los primeros 100 obtienen 3 meses de Premium gratis.
              </p>
            </div>
          </div>

          {/* Right column — iPhone with perspective tilt */}
          {/*
            data-hero-phone is on this outer wrapper div.
            GSAP animates y + scale on THIS element only.
            The perspective container and the rotateY/rotateX div are children —
            their CSS 3D transforms are completely untouched by GSAP.
          */}
          <div
            data-hero-phone
            className="flex justify-center md:justify-end items-center"
          >
            {/*
              Perspective wrapper: creates 3D context for child transform.
              The phone tilts slightly (rotateY -14deg, rotateX 6deg, rotate 2deg)
              giving a natural "held in hand" presentation angle.
              motion-safe gates the hover ease transition.
            */}
            <div aria-hidden="true" className="[perspective:1200px]">
              <div
                className="
                  w-[240px] sm:w-[270px] lg:w-[310px]
                  [transform:rotateY(-14deg)_rotateX(6deg)_rotate(2deg)]
                  hover:[transform:rotateY(-6deg)_rotateX(3deg)_rotate(1deg)]
                  motion-safe:transition-transform motion-safe:duration-500 motion-safe:ease-out
                  drop-shadow-[0_24px_40px_rgba(0,0,0,0.14)]
                "
              >
                <Iphone src="/img/img.png" />
              </div>
            </div>
            {/* Accessible text alternative for the phone visual */}
            <span className="sr-only">
              Vista previa de la interfaz de chat de CycloAI en un iPhone
            </span>
          </div>
        </HeroIntro>
      </Container>
    </section>
  );
}
