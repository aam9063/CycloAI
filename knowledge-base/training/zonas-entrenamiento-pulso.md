---
title: Zonas de entrenamiento por pulso (LTHR)
category: training
keywords:
  [
    pulso,
    frecuencia cardíaca,
    LTHR,
    umbral de lactato,
    zonas de pulso,
    Friel,
    sin potenciómetro,
    ppm,
    bpm,
  ]
---

## Por qué existe este documento, y en qué se diferencia del de potencia

La knowledge base tenía un solo modelo de zonas: el de Coggan, expresado en **%FTP** (potencia). Ese modelo asume que el ciclista tiene **potenciómetro**.

Un potenciómetro es un accesorio caro, y muchísimas bicicletas no lo tienen. Si el sistema solo sabe prescribir por potencia, deja afuera a la mayoría de los ciclistas. La frecuencia cardíaca, en cambio, se mide con cualquier banda de pecho o reloj, y es la alternativa realista.

Por eso hay **dos modelos de zonas, y no son intercambiables**:

| | Potencia | Pulso |
| --- | --- | --- |
| Documento | `zonas-entrenamiento-potencia.md` | este |
| Referencia | Coggan (%FTP) | Friel (%LTHR) |
| Ancla fisiológica | FTP (potencia umbral) | LTHR (pulso umbral) |
| Requiere | potenciómetro | banda de pecho o reloj |
| Bandas | Z1–Z7 | Z1–Z4 + Z5a/Z5b/Z5c |

**El mismo código de zona significa cosas distintas en cada modelo.** `Z2` es una banda de potencia en un caso y una banda de pulso en el otro. Cualquier código de zona que circule por el sistema debe llevar explícito a qué modelo pertenece.

**No existe un factor de conversión válido entre pulso y potencia.** La relación entre ambos es individual, cambia con la forma física, con la fatiga, con la temperatura y con la duración; y en esfuerzos cortos ni siquiera hay relación estable, porque el pulso reacciona tarde. Convertir con un factor fijo sería precisión inventada. El sistema prescribe en el modelo que el atleta declaró, y no traduce.

## Las siete bandas de pulso (modelo de Friel)

Joe Friel popularizó un modelo de cinco zonas en el que la zona 5 se subdivide en 5a, 5b y 5c, por lo que en la práctica se muestra como siete. Las zonas 1 a 4 son idénticas en ambas vistas.

Bandas para ciclismo, en porcentaje del **LTHR** (pulso de umbral de lactato):

| Zona | Nombre | % del LTHR | Qué entrena | RPE |
| --- | --- | --- | --- | --- |
| Z1 | Recuperación (Recovery) | menos de 81% | Recuperación activa, soltar las piernas | 1–2 |
| Z2 | Aeróbico (Aerobic) | 81–89% | Base aeróbica, metabolismo de grasas | 3–4 |
| Z3 | Tempo (Tempo) | 90–93% | Resistencia aeróbica, trabajo sostenido "cómodo duro" | 5–6 |
| Z4 | Subumbral (SubThreshold) | 94–99% | Umbral de lactato; lo más duro sostenible | 7–8 |
| Z5a | Superumbral (SuperThreshold) | 100–102% | Recién por encima del umbral | 9 |
| Z5b | Capacidad aeróbica (Aerobic Capacity) | 103–106% | Potencia aeróbica máxima | 9–10 |
| Z5c | Capacidad anaeróbica (Anaerobic Capacity) | más de 106% | Esfuerzos cortos y agudos | 10 |

Fuente: Joe Friel, *Quick Guide to Setting Training Zones* (artículo del autor en TrainingPeaks y en su blog trainingbible.com). Friel publica exactamente `Zone 5a: 100% to 102% of LTHR`, `Zone 5b: 103% to 106% of LTHR`, `Zone 5c: More than 106% of LTHR`, y para ciclismo `Zone 1: less than 81%`, `Zone 2: 81–89%`, `Zone 3: 90–93%`, `Zone 4: 94–99%`. El mismo modelo está implementado en plataformas como intervals.icu (que usa los mismos porcentajes y los renumera Z1–Z7) y en relojes como los Stages.

Advertencia sobre las etiquetas: las palabras que nombran las bandas cambian entre ediciones y plataformas. "SuperThreshold", "Aerobic Capacity" y "Anaerobic Capacity" (las que usa el corpus de este proyecto) son una de las variantes conocidas; otras fuentes llaman a estas bandas "Threshold", "VO2max" y "Power/Sprint". Los **porcentajes** son lo estable; los nombres, no.

## Cómo se obtiene el LTHR

Test de campo, en un tramo llano o en rodillo, descansado:

1. Calentamiento de 10–15 minutos suave, con un par de aceleraciones cortas.
2. Contrarreloj de 30 minutos a esfuerzo duro y **parejo** (no salir fuerte).
3. Marcar vuelta al minuto 10.
4. El LTHR es el **pulso medio de los últimos 20 minutos**.

Se testea por deporte: pedalear produce un pulso de umbral algo menor que correr. Un LTHR obtenido corriendo no sirve para prescribir en bici.

## Registro del corpus de este proyecto

El corpus de ciclismo de este proyecto (`docs/EJEMPLO DE ENTRENAMIENTO PARA CICLISMO.txt`) prescribe **en pulso**, con targets del tipo `30 min @ 67 bpm`, y usa los códigos Z1–Z4 más `5A`, `5B` y `5C` con las etiquetas del modelo de Friel.

Lo que se midió: extrayendo cada par duración–zona del corpus, las bandas observadas son contiguas y monótonas.

| Zona | Etiqueta en el corpus | bpm observados |
| --- | --- | --- |
| Z1 | Recovery | 67–118 |
| Z2 | Aerobic | 123–129 |
| Z3 | Tempo | 133–136 |
| Z4 | SubThreshold | 139–145 |
| Z5a | SuperThreshold | 148–149 |
| Z5b | Aerobic Capacity | 152–155 |
| Z5c | Anaerobic Capacity | 163–222 |

Verificación: si se toma cada banda observada como restricción sobre el LTHR desconocido de ese atleta, las siete restricciones son mutuamente compatibles con **un único LTHR entre 145 y 149 bpm**. Que siete bandas independientes intersecten en un intervalo estrecho y no vacío confirma que el corpus pertenece a este modelo y no a otro. Este es el ejemplo trabajado de **un** atleta; no es una banda general, y el LTHR de otra persona dará otros números.

## El límite real del pulso: reacciona tarde

El pulso es un indicador **retrasado**. Ante un cambio brusco de esfuerzo tarda del orden de 30 a 60 segundos en reflejarlo. Consecuencias prácticas:

- En intervalos de menos de un minuto, prescribir por pulso es engañoso: cuando el pulso llega al valor objetivo, el esfuerzo ya terminó. Para esos esfuerzos se prescribe por **percepción (RPE)** o por potencia.
- El pulso **deriva**: a potencia constante sube con el calor, la deshidratación y la duración. Un mismo pulso puede significar potencias distintas al minuto 10 y al minuto 90.
- Varía día a día por sueño, cafeína, estrés y temperatura. Un pulso alto en un día caluroso no significa sobreentrenamiento.

Este límite explica por qué el corpus mezcla notación: la mayoría de sus pasos tienen target en bpm, pero sus esfuerzos muy cortos (20–40 segundos en Z5a/Z5b) apuntan con **RPE** en lugar de pulso, y llevan anotaciones del propio autor como `NO TIENES QUE LLEGAR A ESTE PULSO` y `A TOPE`. Es decir: el autor ya sabía que en esos esfuerzos el pulso no sirve como objetivo.

Regla que se desprende: **de un minuto hacia arriba, pulso; por debajo, RPE.** Y en cualquier caso, "no llegar al pulso objetivo" en esfuerzos máximos no es un error de ejecución, es la naturaleza del sistema.

## Cuándo conviene cada modelo

- **Sin potenciómetro**: pulso, con este documento. Es la única opción real y es perfectamente entrenable.
- **Con potenciómetro**: potencia, con `zonas-entrenamiento-potencia.md`. Es la medida directa del trabajo, no tiene retraso ni deriva, y es la referencia para intervalos cortos.
- **Nunca los dos mezclados en un mismo plan como si fueran equivalentes.** Elegir un modelo por atleta y prescribir en él.
