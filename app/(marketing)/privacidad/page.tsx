import type { Metadata } from "next";
import Link from "next/link";
import Container from "@/components/ui/Container";

export const metadata: Metadata = {
  title: "Política de privacidad — CycloAI",
  description:
    "Información sobre cómo CycloAI recoge, trata y protege sus datos personales, incluyendo datos de salud, conforme al Reglamento General de Protección de Datos (RGPD).",
};

export default function PrivacidadPage() {
  return (
    <div className="bg-canvas py-16 min-h-screen">
      <Container>
        <div className="mx-auto max-w-3xl">
          {/* Header */}
          <h1 className="display-md text-ink mb-2">Política de privacidad</h1>
          <p className="text-[13px] text-ink-mute mb-10">
            Última actualización: junio de 2026
          </p>

          <div className="space-y-10 text-[15px] leading-relaxed text-ink-mute text-justify">

            {/* 1. Responsable */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                1. Responsable del tratamiento
              </h2>
              <p>
                {/* TODO: completar con los datos reales del titular */}
                <strong className="text-ink">CycloAI</strong> —&nbsp;
                [Nombre completo del titular o razón social], con domicilio en [dirección],
                y correo de contacto:{" "}
                <a
                  href="mailto:[email de contacto]"
                  className="text-ink underline underline-offset-2 hover:text-primary"
                >
                  [email de contacto]
                </a>
                .
              </p>
              <p className="mt-2 text-[13px] bg-canvas-soft border border-hairline rounded-md px-4 py-3">
                <strong>Nota:</strong> Los campos entre corchetes son marcadores de posición que el
                titular debe completar antes de la puesta en producción del servicio.
              </p>
            </section>

            {/* 2. Datos recogidos */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                2. Datos personales que se recogen
              </h2>

              <h3 className="text-[15px] font-medium text-ink mb-2">
                2.1 Datos de cuenta
              </h3>
              <p>
                Al registrarse, se recogen nombre o nombre de usuario, dirección de correo
                electrónico y, en el caso de autenticación con contraseña, un hash criptográfico
                de la misma. Si se utiliza el inicio de sesión con Google, se reciben únicamente
                el nombre y el correo que Google proporciona de forma estándar.
              </p>

              <h3 className="text-[15px] font-medium text-ink mt-4 mb-2">
                2.2 Perfil deportivo del proceso de incorporación (<em>onboarding</em>)
              </h3>
              <p>
                Durante el proceso de incorporación se solicitan datos relativos a su actividad
                como ciclista: objetivo deportivo principal, disponibilidad horaria semanal, días
                de acceso a gimnasio, uso de medidor de potencia y potencia umbral funcional (FTP)
                aproximada, así como el evento o carrera objetivo que tenga previsto.
              </p>

              {/* Health data — highlighted */}
              <div className="mt-4 border-l-4 border-primary pl-4 bg-canvas-soft rounded-r-md py-3 pr-4">
                <h3 className="text-[15px] font-medium text-ink mb-2">
                  2.3 Datos de salud: lesiones y limitaciones físicas (categoría especial — art. 9
                  RGPD)
                </h3>
                <p>
                  En el proceso de incorporación se solicita información sobre lesiones actuales,
                  zonas de dolor recurrente u otras limitaciones físicas relevantes para la
                  planificación del entrenamiento. Estos datos constituyen{" "}
                  <strong className="text-ink">datos relativos a la salud</strong>, calificados
                  como <strong className="text-ink">categoría especial</strong> conforme al
                  artículo 9 del Reglamento (UE) 2016/679 (RGPD).
                </p>
                <p className="mt-2">
                  Dichos datos se tratan <strong className="text-ink">únicamente</strong> con el
                  consentimiento explícito del usuario y con la exclusiva finalidad de personalizar
                  las recomendaciones de entrenamiento, evitar cargas que puedan agravar lesiones
                  existentes y adaptar los planes de gimnasio a las limitaciones declaradas.{" "}
                  <strong className="text-ink">No se ceden a terceros</strong> ni se utilizan con
                  ninguna otra finalidad.
                </p>
              </div>

              <h3 className="text-[15px] font-medium text-ink mt-4 mb-2">
                2.4 Conversaciones del chat
              </h3>
              <p>
                Los mensajes intercambiados con el asistente de IA se almacenan para permitir la
                continuidad de las conversaciones entre sesiones y mejorar la personalización de
                las respuestas. Las conversaciones se envían a la API de Google Gemini para generar
                las respuestas del asistente; Google, como encargado del tratamiento, procesa estos
                datos conforme a sus condiciones de uso de la API (véase el apartado 4).
              </p>

              <h3 className="text-[15px] font-medium text-ink mt-4 mb-2">
                2.5 Datos de pago
              </h3>
              <p>
                Los pagos correspondientes a los planes de suscripción de pago se procesan a través
                de Stripe y Lemon Squeezy. CycloAI{" "}
                <strong className="text-ink">no almacena</strong> en ningún momento números de
                tarjeta ni datos financieros sensibles. Los procesadores de pago actúan como
                responsables independientes del tratamiento de los datos de pago.
              </p>

              <h3 className="text-[15px] font-medium text-ink mt-4 mb-2">
                2.6 Datos de Strava (tratamiento futuro, condicionado a conexión voluntaria)
              </h3>
              <p>
                CycloAI ofrecerá próximamente la posibilidad de conectar la cuenta de Strava del
                usuario. Esta integración es estrictamente voluntaria: solo se activará si el
                usuario decide conectarla expresamente desde su perfil. En caso de conexión, se
                accederá a actividades, datos de potencia y frecuencia cardíaca con el único fin de
                calcular métricas de rendimiento (FTP, CTL, ATL, TSB) y personalizar las
                recomendaciones. El usuario puede revocar el acceso en cualquier momento desde su
                perfil, lo que eliminará los tokens de acceso de los servidores de CycloAI.
              </p>
            </section>

            {/* 3. Finalidades y bases legales */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                3. Finalidades del tratamiento y bases jurídicas
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-[14px] border-collapse">
                  <thead>
                    <tr className="border-b border-hairline">
                      <th className="text-left font-medium text-ink py-2 pr-4">Finalidad</th>
                      <th className="text-left font-medium text-ink py-2 pr-4">Base legal (RGPD)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline-cool">
                    <tr>
                      <td className="py-2 pr-4">Prestación del servicio de entrenamiento personalizado</td>
                      <td className="py-2">Art. 6.1.b — ejecución del contrato</td>
                    </tr>
                    <tr>
                      <td className="py-2 pr-4">
                        Tratamiento de datos de salud (lesiones y limitaciones físicas)
                      </td>
                      <td className="py-2">
                        Art. 9.2.a — consentimiento explícito del interesado
                      </td>
                    </tr>
                    <tr>
                      <td className="py-2 pr-4">Personalización de recomendaciones con datos de Strava</td>
                      <td className="py-2">Art. 6.1.a — consentimiento del interesado</td>
                    </tr>
                    <tr>
                      <td className="py-2 pr-4">Seguridad del servicio y prevención del fraude</td>
                      <td className="py-2">Art. 6.1.f — interés legítimo</td>
                    </tr>
                    <tr>
                      <td className="py-2 pr-4">Gestión de pagos y suscripciones</td>
                      <td className="py-2">Art. 6.1.b — ejecución del contrato</td>
                    </tr>
                    <tr>
                      <td className="py-2 pr-4">Cumplimiento de obligaciones legales</td>
                      <td className="py-2">Art. 6.1.c — obligación legal</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            {/* 4. Encargados / destinatarios */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                4. Encargados del tratamiento y destinatarios
              </h2>
              <p className="mb-3">
                CycloAI no vende datos personales a terceros. Los datos se comparten únicamente con
                los siguientes encargados del tratamiento, en la medida necesaria para prestar el
                servicio:
              </p>
              <ul className="space-y-3 list-none pl-0">
                <li className="border-l-2 border-hairline pl-4">
                  <strong className="text-ink">Supabase</strong> — base de datos y autenticación.
                  Los datos se almacenan en la región{" "}
                  <strong className="text-ink">eu-west-3 (París, Francia)</strong>, dentro de la
                  Unión Europea, con garantías adecuadas conforme al RGPD.
                </li>
                <li className="border-l-2 border-hairline pl-4">
                  <strong className="text-ink">Google (API de Gemini)</strong> — procesamiento de
                  inteligencia artificial. Las conversaciones del chat se envían a la API de Google
                  Gemini para generar respuestas. Según las condiciones de servicio de la API de
                  Google para desarrolladores, Google no utiliza el contenido enviado a través de
                  la API de pago para entrenar sus modelos de IA generativa. Los usuarios deben
                  consultar las condiciones vigentes de Google para información actualizada.
                </li>
                <li className="border-l-2 border-hairline pl-4">
                  <strong className="text-ink">Vercel</strong> — infraestructura de alojamiento
                  (<em>hosting</em>) y entrega de la aplicación web.
                </li>
                <li className="border-l-2 border-hairline pl-4">
                  <strong className="text-ink">Stripe</strong> y{" "}
                  <strong className="text-ink">Lemon Squeezy</strong> — procesamiento de pagos y
                  gestión de suscripciones. Estos proveedores actúan como responsables
                  independientes respecto a los datos de pago que reciben directamente del usuario.
                </li>
              </ul>
            </section>

            {/* 5. Conservación */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                5. Plazo de conservación
              </h2>
              <p>
                Los datos se conservan mientras la cuenta permanezca activa. Al eliminar la cuenta
                desde la sección de perfil (<code className="text-[14px] bg-canvas-soft px-1 rounded">/profile</code>),
                todos los datos asociados —incluidos conversaciones, perfil deportivo, datos de
                salud y tokens de acceso de Strava— se eliminan de forma completa e inmediata de
                los sistemas de CycloAI.
              </p>
              <p className="mt-2">
                Los datos de pago históricos pueden conservarse durante el plazo legalmente exigido
                por la normativa fiscal y contable aplicable (generalmente cuatro años en España).
              </p>
            </section>

            {/* 6. Derechos */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                6. Derechos del interesado
              </h2>
              <p className="mb-3">
                Conforme al RGPD, el usuario puede ejercer en cualquier momento los siguientes
                derechos dirigiéndose al correo de contacto indicado en el apartado 1:
              </p>
              <ul className="space-y-1 list-disc list-inside">
                <li>
                  <strong className="text-ink">Acceso</strong>: conocer qué datos se tratan y
                  obtener una copia.
                </li>
                <li>
                  <strong className="text-ink">Rectificación</strong>: corregir datos inexactos o
                  incompletos.
                </li>
                <li>
                  <strong className="text-ink">Supresión</strong>: solicitar la eliminación de los
                  datos (o hacerlo directamente desde <code className="text-[14px] bg-canvas-soft px-1 rounded">/profile</code>).
                </li>
                <li>
                  <strong className="text-ink">Portabilidad</strong>: recibir los datos en formato
                  estructurado y de uso común.
                </li>
                <li>
                  <strong className="text-ink">Oposición</strong>: oponerse al tratamiento basado
                  en interés legítimo.
                </li>
                <li>
                  <strong className="text-ink">Limitación</strong>: solicitar la restricción del
                  tratamiento en los supuestos previstos por el RGPD.
                </li>
                <li>
                  <strong className="text-ink">Retirada del consentimiento</strong>: en cualquier
                  momento, sin que ello afecte a la licitud del tratamiento anterior.
                </li>
              </ul>
              <p className="mt-3">
                Si considera que el tratamiento de sus datos vulnera la normativa aplicable, tiene
                derecho a presentar una reclamación ante la{" "}
                <strong className="text-ink">
                  Agencia Española de Protección de Datos (AEPD)
                </strong>{" "}
                (<a
                  href="https://www.aepd.es"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-ink underline underline-offset-2 hover:text-primary"
                >
                  www.aepd.es
                </a>
                ).
              </p>
            </section>

            {/* 7. Cookies */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                7. Cookies y tecnologías similares
              </h2>
              <p>
                CycloAI utiliza únicamente cookies de sesión estrictamente necesarias para el
                funcionamiento de la autenticación (gestionadas por Supabase Auth). No se utilizan
                cookies de publicidad, rastreo entre sitios ni analítica de terceros. No se
                requiere consentimiento para estas cookies al ser imprescindibles para la prestación
                del servicio solicitado.
              </p>
            </section>

            {/* 8. Menores */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                8. Menores de edad
              </h2>
              <p>
                CycloAI no está dirigido a personas menores de 16 años. No se recogen ni tratan
                conscientemente datos de menores. Si tiene conocimiento de que un menor ha
                proporcionado datos personales, le rogamos que lo comunique al correo de contacto
                para proceder a su eliminación.
              </p>
            </section>

            {/* 9. Cambios */}
            <section>
              <h2 className="text-[18px] font-medium text-ink mt-10 mb-3">
                9. Cambios en la política de privacidad
              </h2>
              <p>
                CycloAI puede actualizar esta política para reflejar cambios en el servicio o en la
                normativa aplicable. Cuando los cambios sean sustanciales, se notificará a los
                usuarios registrados por correo electrónico o mediante un aviso visible en la
                aplicación. La fecha de última actualización figura al inicio de esta página.
              </p>
            </section>

            {/* Cross-link */}
            <div className="border-t border-hairline pt-8 mt-10">
              <p className="text-[14px]">
                Consulte también nuestros{" "}
                <Link
                  href="/terminos"
                  className="text-ink underline underline-offset-2 hover:text-primary motion-safe:transition-colors"
                >
                  Términos de uso
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
