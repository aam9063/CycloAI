import Container from "@/components/ui/Container";
import Button from "@/components/ui/Button";

export default function CtaSection() {
  return (
    <section className="py-24 bg-canvas-night">
      <Container className="text-center">
        <h2 className="display-lg text-on-dark mb-4">
          ¿Listo para entrenar con datos reales?
        </h2>
        <p className="text-[18px] leading-[1.55] text-on-dark/70 mb-8 max-w-md mx-auto">
          Conecta Strava en 30 segundos y empieza hoy.
        </p>
        <Button variant="primary" href="/login">
          Empezar gratis
        </Button>
      </Container>
    </section>
  );
}
