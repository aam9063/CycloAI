import type { Metadata } from "next";
import Link from "next/link";
import Container from "@/components/ui/Container";

export const metadata: Metadata = {
  title: "Términos de uso — CycloAI",
  description:
    "Condiciones que regulan el acceso y uso del servicio CycloAI, incluyendo suscripciones, limitaciones de responsabilidad y descargo médico-deportivo.",
};

export default function TerminosPage() {
  return (
    <div className="bg-canvas py-16 min-h-screen">
      <Container>
        <div className="mx-auto max-w-3xl">
          {/* Header */}
          <h1 className="display-md text-ink mb-2">Términos de uso</h1>
          <p className="text-[13px] text-ink-mute mb-10">
            Última actualización: junio de 2026
          </p>

          <div className="space-y-10 text-[15px] leading-relaxed text-ink-mute text-justify">

            {/* 1. Descripción del servicio */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                1. Descripción del servicio
              </h2>
              <p>
                CycloAI es una aplicación web progresiva (PWA) que proporciona recomendaciones
                personalizadas de entrenamiento ciclista, preparación física y nutrición mediante
                inteligencia artificial. El servicio incluye una interfaz de chat, planes de
                entrenamiento generados por IA, integración opcional con plataformas de actividad
                deportiva y herramientas de seguimiento de rendimiento.
              </p>
              <p className="mt-2">
                El acceso al servicio requiere la creación de una cuenta. Al registrarse, el
                usuario acepta estos términos en su totalidad.
              </p>
            </section>

            {/* 2. Cuenta */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                2. Registro y responsabilidad de la cuenta
              </h2>
              <p>
                El usuario es responsable de mantener la confidencialidad de sus credenciales de
                acceso y de todas las actividades realizadas desde su cuenta. CycloAI no será
                responsable de los daños derivados del acceso no autorizado provocado por una
                custodia negligente de las credenciales.
              </p>
              <p className="mt-2">
                El usuario debe proporcionar información veraz durante el registro y el proceso de
                incorporación. La introducción de datos falsos o inexactos puede afectar a la
                calidad de las recomendaciones generadas.
              </p>
            </section>

            {/* 3. Planes y pagos */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                3. Planes de suscripción y pagos
              </h2>
              <p>CycloAI ofrece los siguientes planes:</p>
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>
                  <strong className="text-ink">Free</strong>: acceso limitado sin coste mensual.
                </li>
                <li>
                  <strong className="text-ink">Pro</strong>: acceso ampliado por 5&nbsp;€/mes, o
                  45&nbsp;€/año con facturación anual.
                </li>
                <li>
                  <strong className="text-ink">Premium</strong>: acceso completo por 9,99&nbsp;€/mes,
                  o 70&nbsp;€/año con facturación anual.
                </li>
              </ul>
              <p className="mt-3">
                Los pagos correspondientes a los planes Pro y Premium se procesan a través de
                Stripe y Lemon Squeezy. La suscripción se renueva automáticamente al inicio de
                cada período salvo que el usuario la cancele antes de la fecha de renovación. La
                cancelación es efectiva al término del período ya abonado; no se realizan
                reembolsos por el período en curso salvo que la ley aplicable lo exija.
              </p>
              <p className="mt-2">
                Los precios indicados son orientativos para la fase MVP y pueden modificarse con
                el preaviso razonable establecido en el apartado 9.
              </p>
              <p className="mt-2">
                <strong className="text-ink">Sin permanencia</strong>: el usuario puede cancelar
                su suscripción en cualquier momento desde la sección de perfil de la aplicación.
              </p>
            </section>

            {/* 4. MEDICAL DISCLAIMER — highlighted */}
            <section>
              <div className="border-l-4 border-primary pl-4 bg-canvas-soft rounded-r-md py-4 pr-4">
                <h2 className="text-[18px] font-medium text-ink mb-3">
                  4. Descargo de responsabilidad deportivo y médico
                </h2>
                <p>
                  <strong className="text-ink">
                    CycloAI no es un servicio médico ni un sustituto del asesoramiento
                    profesional sanitario o de un entrenador titulado.
                  </strong>
                </p>
                <p className="mt-3">
                  Los planes de entrenamiento, rutinas de gimnasio y recomendaciones de nutrición
                  generados por CycloAI son producidos por un sistema de inteligencia artificial
                  con fines{" "}
                  <strong className="text-ink">exclusivamente informativos</strong>. No constituyen
                  diagnóstico médico, prescripción terapéutica ni consejo clínico de ningún tipo.
                </p>
                <p className="mt-3">
                  <strong className="text-ink">
                    Antes de iniciar cualquier programa de entrenamiento, modificar su dieta o
                    ejercitarse con lesiones o condiciones de salud preexistentes, consulte a un
                    médico u otro profesional sanitario habilitado.
                  </strong>{" "}
                  Esto es especialmente relevante en caso de enfermedades cardiovasculares,
                  metabólicas, musculoesqueléticas u otras condiciones que puedan verse afectadas
                  por el ejercicio físico.
                </p>
                <p className="mt-3">
                  El usuario entrena y sigue las recomendaciones de CycloAI bajo su{" "}
                  <strong className="text-ink">propia responsabilidad</strong>. CycloAI no asume
                  responsabilidad por lesiones, daños a la salud, pérdida de rendimiento u otros
                  perjuicios derivados de seguir, adaptar o ignorar las recomendaciones generadas.
                </p>
                <p className="mt-3">
                  La inteligencia artificial puede cometer errores. Las recomendaciones deben
                  tratarse como una orientación de partida, no como instrucciones definitivas.
                  El usuario debe aplicar su criterio personal y, cuando tenga dudas, consultar
                  a un profesional.
                </p>
              </div>
            </section>

            {/* 5. Uso aceptable */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                5. Uso aceptable
              </h2>
              <p>El usuario se compromete a no:</p>
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>
                  Acceder al servicio de forma automatizada (<em>scraping</em>, bots) sin
                  autorización escrita de CycloAI.
                </li>
                <li>
                  Revender, sublicenciar o redistribuir el acceso al servicio a terceros.
                </li>
                <li>
                  Intentar eludir las medidas de seguridad técnicas o los límites de uso del plan
                  contratado.
                </li>
                <li>
                  Introducir contenido ilegal, ofensivo o que infrinja derechos de terceros en las
                  conversaciones del chat.
                </li>
                <li>
                  Utilizar el servicio para fines distintos al entrenamiento deportivo personal.
                </li>
              </ul>
            </section>

            {/* 6. Propiedad intelectual */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                6. Propiedad intelectual
              </h2>
              <p>
                Todo el software, diseño, marca, textos y contenidos de CycloAI son propiedad de
                sus titulares o licenciantes y están protegidos por la normativa de propiedad
                intelectual e industrial aplicable. El usuario recibe únicamente una licencia de
                uso personal, no exclusiva, intransferible y revocable para acceder al servicio.
              </p>
              <p className="mt-2">
                Los planes, rutinas y conversaciones generados a partir de los datos del usuario
                son de uso personal. CycloAI no reivindica la titularidad sobre el contenido
                introducido por el usuario en el chat.
              </p>
            </section>

            {/* 7. Disponibilidad */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                7. Disponibilidad del servicio
              </h2>
              <p>
                CycloAI se ofrece actualmente en fase de producto mínimo viable (MVP). CycloAI no
                garantiza disponibilidad continua, ininterrumpida ni libre de errores. El servicio
                puede experimentar interrupciones por mantenimiento, actualizaciones u otras causas
                ajenas al control de CycloAI.
              </p>
            </section>

            {/* 8. Limitación de responsabilidad */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                8. Limitación de responsabilidad
              </h2>
              <p>
                En la máxima medida permitida por la legislación aplicable, CycloAI no será
                responsable por daños indirectos, incidentales, especiales o consecuentes,
                incluidos pérdida de datos, lucro cesante o daños derivados de la interrupción del
                servicio. La responsabilidad total de CycloAI frente al usuario no excederá, en
                ningún caso, el importe abonado por el usuario en los tres meses anteriores al
                hecho generador de la reclamación.
              </p>
              <p className="mt-2">
                Esta limitación no excluye ni restringe la responsabilidad de CycloAI en los
                supuestos en que la ley no lo permite (como dolo, culpa grave o daños a
                consumidores en virtud del Real Decreto Legislativo 1/2007).
              </p>
            </section>

            {/* 9. Terminación */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                9. Terminación
              </h2>
              <p>
                El usuario puede dar de baja su cuenta en cualquier momento desde la sección de
                perfil. CycloAI se reserva el derecho a suspender o cancelar cuentas que incumplan
                estos términos, previa notificación salvo en casos de infracción grave.
              </p>
            </section>

            {/* 10. Cambios en los términos */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                10. Cambios en los términos de uso
              </h2>
              <p>
                CycloAI puede actualizar estos términos para reflejar cambios en el servicio, en
                la normativa aplicable o en el modelo de negocio. Los cambios sustanciales se
                comunicarán con al menos 30 días de antelación por correo electrónico o aviso en
                la aplicación. El uso continuado del servicio tras la entrada en vigor de los
                nuevos términos implicará su aceptación.
              </p>
            </section>

            {/* 11. Ley aplicable */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                11. Ley aplicable y jurisdicción
              </h2>
              <p>
                Estos términos se rigen por la legislación española. Para la resolución de
                controversias derivadas de su interpretación o ejecución, las partes se someten a
                los juzgados y tribunales del domicilio del usuario cuando este tenga la condición
                de consumidor, conforme a lo establecido en la normativa de protección de
                consumidores y usuarios vigente en España.
              </p>
            </section>

            {/* Cross-link */}
            <div className="border-t border-hairline pt-8 mt-10">
              <p className="text-[14px]">
                Consulte también nuestra{" "}
                <Link
                  href="/privacidad"
                  className="text-ink underline underline-offset-2 hover:text-primary motion-safe:transition-colors"
                >
                  Política de privacidad
                </Link>
                .
              </p>
            </div>

          </div>
        </div>
      </Container>
    </div>
  );
}
