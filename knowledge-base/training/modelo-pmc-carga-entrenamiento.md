---
title: "Modelo PMC de carga de entrenamiento: CTL, ATL y TSB"
category: training
keywords: [pmc, ctl, atl, tsb, tss, carga crónica, fatiga aguda, forma, rendimiento, ewma, fitness, frescura]
---

El Performance Management Chart (PMC) es el modelo cuantitativo más utilizado en ciclismo con potenciómetro para monitorizar la carga de entrenamiento, la fatiga acumulada y la forma deportiva en el tiempo. Desarrollado originalmente por Eric Banister y adaptado al ciclismo por Andrew Coggan y Hunter Allen, el modelo transforma el TSS (Training Stress Score) de cada sesión en tres métricas derivadas que permiten planificar con precisión cuándo cargar, cuándo descansar y cuándo llegar a un evento con la máxima frescura.

## Las tres métricas del modelo PMC

CTL (Chronic Training Load — Carga Crónica): media móvil exponencial del TSS diario con una constante de tiempo de 42 días. Representa el nivel de forma física actual del atleta. Un CTL alto indica que el atleta ha acumulado mucho entrenamiento en los últimos meses; un CTL bajo indica poco entrenamiento reciente o un período de descanso prolongado. La constante de 42 días significa que el CTL refleja el entrenamiento de las últimas 6 semanas, con peso decreciente para los días más lejanos. El CTL cambia lentamente: subir 5 puntos de CTL requiere varias semanas de carga sostenida; bajar es más rápido, especialmente con descanso prolongado.

ATL (Acute Training Load — Carga Aguda): media móvil exponencial del TSS diario con una constante de tiempo de 7 días. Representa la fatiga acumulada en la última semana. El ATL reacciona rápido: una sesión de 200 puntos de TSS sube el ATL de forma notable al día siguiente. El ATL también baja rápido: 3-4 días de descanso pueden reducirlo significativamente.

TSB (Training Stress Balance — Balance de Entrenamiento): diferencia entre CTL y ATL del día anterior:

TSB = CTL(ayer) - ATL(ayer)

TSB negativo: la fatiga acumulada (ATL) supera la forma base (CTL). El atleta está entrenando o acaba de entrenar fuerte. TSB positivo: la fatiga ha bajado y el atleta está "fresco" respecto a su nivel de forma base. TSB positivo alto (>+20) con CTL bajo puede indicar desentrenamiento, no forma pico.

## Cómo se calcula la media móvil exponencial (EWMA)

La fórmula de actualización diaria usa el factor de suavizado derivado de la constante de tiempo:

- Para CTL (τ = 42 días): factor α = 2 / (42 + 1) ≈ 0,0465
- Para ATL (τ = 7 días): factor α = 2 / (7 + 1) = 0,25

CTL(hoy) = CTL(ayer) × (1 - 0,0465) + TSS(hoy) × 0,0465
ATL(hoy) = ATL(ayer) × (1 - 0,25) + TSS(hoy) × 0,25

En un día de descanso (TSS = 0):
CTL(hoy) = CTL(ayer) × 0,9535
ATL(hoy) = ATL(ayer) × 0,75

El ATL cae un 25% cada día de descanso; el CTL cae solo un 4,65% al día. Por eso la fatiga se disipa mucho más rápido que la forma.

## Interpretación práctica del TSB

Las bandas de interpretación del TSB son orientativas y varían entre atletas, pero los rangos habituales son:

TSB entre +25 y +10: óptimo para rendimiento pico. El atleta está fresco y ha mantenido suficiente carga para no perder adaptaciones. Rango ideal en el día de un evento importante.

TSB entre +10 y -10: zona "normal" de entrenamiento continuo. El atleta puede entrenar bien y recuperarse en 1-2 días de descanso.

TSB entre -10 y -20: fatiga notable. Las sesiones de calidad pueden estar comprometidas. Una semana de recuperación debería llevar el TSB de vuelta a 0 o positivo.

TSB entre -20 y -30: fatiga alta. Riesgo de degradación del rendimiento en los intervalos. No aumentar la carga en este rango; mantenerla como máximo.

TSB inferior a -30: fatiga excesiva. El entrenamiento en este estado produce solo daño sin adaptación. Prioridad: recuperación inmediata.

## Tasa óptima de crecimiento del CTL

El CTL debe crecer, pero a un ritmo sostenible. Las referencias empíricas más aceptadas en ciclismo son:

- Crecimiento conservador: 3-5 puntos de CTL por semana. Apropiado para la fase de base o para atletas con CTL inicial bajo (menos de 40 puntos).
- Crecimiento moderado: 5-7 puntos por semana. Apropiado para atletas con base aeróbica establecida en fase de build.
- Crecimiento agresivo: 7-10 puntos por semana. Solo en atletas con alta tolerancia al entrenamiento y monitorización estrecha del TSB. Sostenible durante 2-3 semanas antes de necesitar una semana de recuperación.
- Crecimiento superior a 10 puntos semanales de CTL de forma sostenida: riesgo elevado de sobreentrenamiento no funcional (NFOR) y lesiones por sobrecarga.

Un atleta que empieza la temporada con CTL de 35 puntos y quiere llegar a un evento de alta exigencia con CTL de 70 necesita aproximadamente 6-8 semanas de carga progresiva bien planificada.

## CTL mínimo para diferentes tipos de eventos

Los valores de CTL no son comparables entre atletas de distinto nivel (un CTL de 70 para un ciclista amateur de 8 horas/semana representa un nivel muy diferente que el CTL de 70 de un profesional), pero como referencia orientativa para ciclistas amateurs:

- Gran fondo de 3-4 horas: CTL mínimo recomendado en el día del evento: 40-55 puntos.
- Gran fondo de 5-7 horas (Quebrantahuesos, L'Étape): CTL mínimo 55-75 puntos.
- Competición amateur (carrera de circuito, criterium): CTL 50-70 puntos con trabajo específico de zona 5 y zona 6 en las semanas previas.
- Temporada completa con varias carreras: CTL de base en invierno de 40-50, pico de temporada de 70-90.

## Limitaciones del modelo PMC

El modelo PMC es una herramienta potente pero no perfecta:

- No distingue entre tipos de fatiga: el mismo TSS de una sesión de umbral de 2 horas y de una salida larga de zona 2 de 3 horas impacta de forma diferente en el sistema nervioso central, el hormonal y el muscular. El modelo los trata igual.
- Depende de un FTP actualizado: si el FTP usado para calcular TSS es incorrecto, todos los valores de CTL, ATL y TSB derivados son incorrectos. Un FTP subestimado hace que el TSS calculado sea bajo y el modelo subestime la carga real.
- No captura el estrés fuera del entrenamiento: el estrés laboral, el sueño insuficiente y el estrés emocional generan fatiga real que el modelo no contabiliza.
- La constante de 42 días es un promedio poblacional, no un valor personalizado: algunos atletas se adaptan más rápido o más lento. La observación del rendimiento real en los intervalos es siempre el complemento necesario a los números del PMC.

## Uso del PMC para planificar el taper

El taper es el proceso de reducir el ATL (fatiga) manteniendo el CTL (forma) para lograr un TSB positivo el día del evento. La fórmula práctica:

Para llegar al evento con TSB entre +10 y +18, hay que reducir la carga de entrenamiento durante 7-14 días antes del evento. Cuánto reducir depende del CTL y ATL actuales:

- Si CTL = 65 y ATL = 80 (TSB = -15), con 10 días de carga reducida (50% del TSS habitual) el ATL bajará aproximadamente a 45-50 y el TSB llegará a +15 a +20, manteniendo el CTL en torno a 62-63.
- Si el CTL es más bajo (menos de 45) o el ATL no está especialmente elevado, el taper puede ser más corto (7 días) y menos agresivo.

Nunca iniciar el taper con TSB más negativo de -25 esperando que una semana de descanso sea suficiente: si el atleta llega con TSB de -30 a 10 días del evento, casi con toda seguridad no llegará fresco. En ese caso se necesita extender el taper a 14 días y aceptar que el CTL bajará algo más de lo deseable.
