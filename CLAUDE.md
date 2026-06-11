# CycloAI — Project Spec (Claude Code)

> Spec-Driven Development con gentle-ai + engram  
> Lee este archivo completo antes de escribir una sola línea de código.  
> Consulta `design.md` para toda decisión de UI/UX. No uses componentes genéricos sin verificar primero si existe un equivalente en el design system del proyecto.

---

## Metodología de trabajo

Este proyecto usa **Spec-Driven Development (SDD)**:

1. **Spec primero**: cada feature tiene una spec en `/specs/` antes de implementarse
2. **Implementa contra la spec**: el código debe satisfacer la spec, no al revés
3. **Verifica antes de marcar done**: ejecuta los casos de prueba definidos en la spec
4. **gentle-ai**: usa el skill gentle-ai para razonar antes de implementar. Ante cualquier decisión de diseño no especificada, pregunta antes de asumir
5. **engram**: usa engram para mantener memoria de decisiones tomadas durante la sesión. Registra en engram toda decisión arquitectónica o de diseño que no estuviera en la spec original

### Flujo por feature

```
1. Lee la spec de la feature en /specs/{feature}.md
2. Llama a engram para verificar si hay decisiones previas relacionadas
3. Implementa en pequeños commits atómicos
4. Verifica contra los acceptance criteria de la spec
5. Registra decisiones nuevas en engram
```

---

## Visión del Producto

**CycloAI** es una PWA con interfaz de chat (estilo Claude AI) que actúa como entrenador personal inteligente para ciclistas de carretera. Combina:

- Onboarding conversacional para construir el perfil del atleta
- Integración con Strava para extraer estado de forma real (FTP, CTL, ATL, TSB)
- IA con Claude API enriquecida con RAG sobre base de conocimiento de ciclismo
- Planes de entrenamiento, gimnasio y nutrición 100% personalizados

**Usuario objetivo**: ciclista amateur serio, 25-45 años, que ya usa Strava, tiene o quiere mejorar su FTP, y no puede pagar un entrenador humano.

---

## Stack Técnico

```
Frontend         Next.js 16.2.9 (App Router) + TypeScript
Estilos          Tailwind CSS — ver design.md para tokens y componentes
Chat streaming   Vercel AI SDK (useChat, useCompletion)
Auth             Supabase Auth (email/password + Google OAuth)
Strava           Strava API v3 REST — integración opcional desde perfil
Base de datos    Supabase (PostgreSQL + pgvector)
IA               Google Gemini 3.5 Flash via AI SDK v6 (ai + @ai-sdk/google + @ai-sdk/react)
Embeddings       Voyage AI (voyage-2) o OpenAI text-embedding-3-small
Caché            Upstash Redis (free tier suficiente para MVP)
Deploy           Vercel (free Hobby tier para MVP)
Testing          Vitest + Playwright
```

### Variables de entorno requeridas

```env
# Supabase
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# Google AI (Gemini 3.5 Flash — server-only, never NEXT_PUBLIC_)
GOOGLE_GENERATIVE_AI_API_KEY=

# Strava OAuth
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=
STRAVA_WEBHOOK_VERIFY_TOKEN=

# Embeddings (elegir uno)
VOYAGE_API_KEY=
# o OPENAI_API_KEY=

# Redis
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=

# App
NEXTAUTH_URL=
NEXTAUTH_SECRET=
```

---

## Estructura de Carpetas

```
cycloai/
├── app/
│   ├── (marketing)/                  # Grupo de rutas públicas (sin auth)
│   │   ├── layout.tsx                # Layout con Navbar + Footer
│   │   └── page.tsx                  # Landing page — ruta raíz "/"
│   ├── (auth)/
│   │   ├── login/
│   │   │   └── page.tsx              # Login: email/contraseña + botón Google
│   │   └── register/
│   │       └── page.tsx              # Registro: email/contraseña + botón Google
│   ├── (app)/
│   │   ├── layout.tsx                # Layout autenticado
│   │   ├── chat/
│   │   │   └── page.tsx              # Página principal — chat interface
│   │   ├── onboarding/
│   │   │   └── page.tsx              # Onboarding conversacional (primer login)
│   │   ├── dashboard/
│   │   │   └── page.tsx              # Métricas CTL/ATL/TSB + resumen
│   │   ├── plans/
│   │   │   └── page.tsx              # Planes guardados
│   │   └── profile/
│   │       └── page.tsx              # Perfil de usuario + sección Conexiones
│   ├── api/
│   │   ├── chat/
│   │   │   └── route.ts              # Handler IA — CORE del sistema
│   │   ├── strava/
│   │   │   ├── connect/route.ts      # Inicia OAuth de Strava (desde perfil)
│   │   │   ├── callback/route.ts     # Callback OAuth Strava → guarda tokens
│   │   │   ├── disconnect/route.ts   # Revoca tokens y desvincula cuenta
│   │   │   ├── sync/route.ts         # Sync manual de actividades
│   │   │   └── webhook/route.ts      # Webhook de nuevas actividades
│   │   └── onboarding/
│   │       └── route.ts              # Guardar respuestas onboarding
│   └── layout.tsx
│
├── components/
│   ├── landing/
│   │   ├── Navbar.tsx                # Navbar con logo + botones Registro/Login
│   │   ├── HeroSection.tsx           # Hero con headline, subheadline y CTA
│   │   ├── FeaturesSection.tsx       # Funcionalidades / About
│   │   ├── PricingSection.tsx        # Tabla de precios (Free / Pro / Premium)
│   │   ├── CtaSection.tsx            # CTA final antes del footer
│   │   └── Footer.tsx                # Footer con links y créditos
│   ├── chat/
│   │   ├── ChatInterface.tsx         # Contenedor principal — ver design.md
│   │   ├── MessageBubble.tsx         # Burbuja de mensaje usuario/AI
│   │   ├── TrainingPlanTable.tsx     # Render especial: planes en tabla
│   │   ├── MetricCard.tsx            # Tarjeta inline de métricas
│   │   └── ChatInput.tsx             # Input + botón enviar
│   ├── dashboard/
│   │   ├── FitnessChart.tsx          # Gráfico CTL/ATL/TSB
│   │   ├── ZoneDistribution.tsx      # Distribución de zonas
│   │   └── WeekSummary.tsx           # Resumen semanal
│   ├── profile/
│   │   ├── ProfileForm.tsx           # Formulario datos personales
│   │   └── StravaConnect.tsx         # Tarjeta de conexión/desconexión Strava
│   └── ui/                           # Componentes base — siempre referencia design.md
│
├── lib/
│   ├── strava/
│   │   ├── client.ts                 # Cliente Strava API con refresh token
│   │   ├── sync.ts                   # Lógica de sync de actividades
│   │   ├── metrics.ts                # Cálculo FTP, CTL, ATL, TSB, zonas
│   │   └── types.ts                  # Types de la Strava API
│   ├── ai/
│   │   ├── system-prompt.ts          # Builder del system prompt dinámico
│   │   ├── rag.ts                    # Búsqueda vectorial + retrieval
│   │   ├── tools.ts                  # Tool calls definitions (Claude API)
│   │   ├── memory.ts                 # Gestión historial y memoria persistente
│   │   └── types.ts
│   ├── db/
│   │   ├── users.ts                  # Queries de usuario y perfil
│   │   ├── activities.ts             # Queries de actividades
│   │   ├── plans.ts                  # Queries de planes guardados
│   │   └── embeddings.ts             # Queries pgvector
│   └── utils/
│       ├── cache.ts                  # Redis helpers
│       └── date.ts                   # Helpers de fecha/tiempo
│
├── knowledge-base/                   # Archivos fuente del RAG (ver RAG_GUIDE.md)
│   ├── training/
│   ├── gym/
│   ├── nutrition/
│   └── physiology/
│
├── specs/                            # Specs SDD por feature
│   ├── landing.md
│   ├── auth.md
│   ├── profile.md
│   ├── onboarding.md
│   ├── strava-sync.md
│   ├── chat-interface.md
│   ├── ai-engine.md
│   ├── rag-system.md
│   └── dashboard.md
│
├── supabase/
│   └── migrations/                   # Migraciones SQL ordenadas
│
└── tests/
    ├── unit/
    └── e2e/
```

---

## Base de Datos — Schema

### Tabla: `profiles`

```sql
create table profiles (
  id uuid references auth.users(id) primary key,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),

  -- Datos básicos
  display_name text,
  avatar_url text,

  -- Strava (null si no ha conectado)
  strava_id bigint unique,
  strava_connected boolean default false,
  strava_connected_at timestamptz,
  -- Los tokens se guardan en tabla separada strava_tokens (ver abajo)

  -- Onboarding
  objective text,                    -- 'gran_fondo' | 'ftp_improvement' | 'weight_loss' | 'climbing' | 'category_upgrade'
  weekly_hours numeric(4,1),
  gym_days_per_week integer,
  injuries text,
  has_power_meter boolean default false,
  target_event text,
  target_event_date date,
  onboarding_completed boolean default false,
  
  -- Caché de métricas Strava (se actualiza en cada sync)
  ftp_estimated integer,             -- vatios
  ctl numeric(6,2),
  atl numeric(6,2),
  tsb numeric(6,2),
  weekly_volume_km numeric(8,2),
  weekly_volume_hours numeric(6,2),
  avg_days_per_week numeric(4,2),
  last_sync_at timestamptz
);
```

### Tabla: `strava_tokens`

Los tokens de Strava se almacenan separados de `profiles` por seguridad (no se exponen en queries generales).

```sql
create table strava_tokens (
  user_id uuid references profiles(id) primary key,
  access_token text not null,
  refresh_token text not null,
  expires_at timestamptz not null,
  scope text,
  updated_at timestamptz default now()
);

-- RLS: solo el propio usuario puede leer sus tokens
alter table strava_tokens enable row level security;
create policy "strava_tokens_owner" on strava_tokens
  using (auth.uid() = user_id);
```

### Tabla: `activities`

```sql
create table activities (
  id bigint primary key,             -- Strava activity ID
  user_id uuid references profiles(id),
  strava_id bigint unique not null,
  
  name text,
  type text,                         -- 'Ride' | 'VirtualRide' | 'WeightTraining' | etc.
  start_date timestamptz,
  duration_seconds integer,
  distance_meters numeric(10,2),
  elevation_meters numeric(8,2),
  avg_power integer,
  normalized_power integer,
  avg_heart_rate integer,
  max_heart_rate integer,
  tss numeric(6,2),                  -- Training Stress Score calculado
  
  raw_data jsonb,                    -- Respuesta completa de Strava
  created_at timestamptz default now()
);

create index activities_user_date on activities(user_id, start_date desc);
```

### Tabla: `conversations`

```sql
create table conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references profiles(id),
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  title text,
  summary text                       -- Resumen generado automáticamente
);
```

### Tabla: `messages`

```sql
create table messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid references conversations(id),
  user_id uuid references profiles(id),
  role text not null,                -- 'user' | 'assistant'
  content text not null,
  created_at timestamptz default now(),
  metadata jsonb                     -- tool_calls, plan_generated, etc.
);

create index messages_conversation on messages(conversation_id, created_at);
```

### Tabla: `plans`

```sql
create table plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references profiles(id),
  conversation_id uuid references conversations(id),
  created_at timestamptz default now(),
  
  type text,                         -- 'training' | 'gym' | 'nutrition' | 'combined'
  title text,
  duration_weeks integer,
  content jsonb,                     -- Plan estructurado
  is_active boolean default false
);
```

### Tabla: `knowledge_embeddings` (RAG)

```sql
-- Requiere extensión: create extension vector;
create table knowledge_embeddings (
  id uuid primary key default gen_random_uuid(),
  content text not null,
  embedding vector(1024),            -- Voyage AI dimension; usar 1536 para OpenAI
  metadata jsonb,                    -- { category, source_file, chunk_index, title }
  created_at timestamptz default now()
);

create index knowledge_embeddings_vector 
  on knowledge_embeddings 
  using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);
```

---

## Core: API Route `/api/chat`

Este es el archivo más importante del proyecto. Implementar con este flujo exacto:

```typescript
// app/api/chat/route.ts

export async function POST(req: Request) {
  // 1. Auth — verificar sesión Supabase
  const { user } = await getServerSession()
  if (!user) return new Response('Unauthorized', { status: 401 })

  // 2. Parse request
  const { messages, conversationId } = await req.json()
  const lastMessage = messages[messages.length - 1].content

  // 3. Cargar perfil completo del usuario
  const profile = await getUserProfile(user.id)

  // 4. Búsqueda RAG — encontrar chunks relevantes
  const ragContext = await searchKnowledgeBase(lastMessage, { topK: 4 })

  // 5. Construir system prompt dinámico
  const systemPrompt = buildSystemPrompt(profile, ragContext)

  // 6. Cargar historial reciente (últimos 20 mensajes)
  const history = await getConversationHistory(conversationId, 20)

  // 7. Llamar a Gemini via AI SDK v6 con streaming
  const result = streamText({
    model: google('gemini-3.5-flash'),
    maxOutputTokens: 2048,
    system: systemPrompt,
    messages: convertToModelMessages(messages),
    abortSignal: req.signal,
    onFinish: async ({ text }) => {
      await insertAssistantMessage({ conversationId, userId: user.id, content: text })
      await touchConversation(conversationId)
    },
  })

  // 8. Persistir mensaje del usuario (ANTES del stream)
  await insertUserMessage({ conversationId, userId: user.id, content: lastMessage })

  // 9. Stream response con X-Conversation-Id header
  return result.toUIMessageStreamResponse({
    headers: { 'X-Conversation-Id': conversationId },
  })
}
```

---

## Core: System Prompt Builder

```typescript
// lib/ai/system-prompt.ts

export function buildSystemPrompt(profile: UserProfile, ragContext: string): string {
  const tsbInterpretation = interpretTSB(profile.tsb)
  const weeklyLoad = interpretWeeklyLoad(profile)

  return `Eres CycloAI, entrenador experto en ciclismo de carretera con conocimientos profundos de fisiología del ejercicio, periodización del entrenamiento, preparación física en gimnasio específica para ciclistas y nutrición deportiva aplicada al ciclismo.

## PERFIL DEL ATLETA
Objetivo principal: ${profile.objective}
Disponibilidad: ${profile.weekly_hours}h/semana | Gimnasio: ${profile.gym_days_per_week} días/semana
Lesiones o limitaciones: ${profile.injuries || 'Ninguna reportada'}
Evento objetivo: ${profile.target_event ? `${profile.target_event} (${formatDate(profile.target_event_date)})` : 'Sin evento específico'}
Medidor de potencia: ${profile.has_power_meter ? 'Sí' : 'No'}

## ESTADO DE FORMA ACTUAL
${profile.strava_connected ? `
Fuente: Strava (sincronizado ${formatDate(profile.last_sync_at)})
FTP estimado: ${profile.ftp_estimated ?? 'No calculado aún'} W
CTL (fitness crónico, 42 días): ${profile.ctl?.toFixed(1) ?? 'N/A'}
ATL (fatiga aguda, 7 días): ${profile.atl?.toFixed(1) ?? 'N/A'}
TSB (forma): ${profile.tsb?.toFixed(1) ?? 'N/A'} → ${tsbInterpretation}
Volumen últimas 4 semanas: ${profile.weekly_volume_km?.toFixed(0) ?? 'N/A'} km / ${profile.weekly_volume_hours?.toFixed(1) ?? 'N/A'} h promedio semanal
Consistencia: ${profile.avg_days_per_week?.toFixed(1) ?? 'N/A'} días/semana (últimas 8 semanas)
` : `
STRAVA NO CONECTADO — No disponemos de datos objetivos de actividad del atleta.
Trabaja con la información del perfil (objetivo, horas disponibles, nivel declarado).
Si el usuario pregunta algo que requiere datos de carga real (FTP, TSS, CTL/ATL/TSB),
indícale amablemente que puede conectar Strava desde su perfil (/profile → sección Conexiones)
para obtener recomendaciones más precisas. No inventes métricas.
`}

${weeklyLoad}

## BASE DE CONOCIMIENTO RELEVANTE
${ragContext}

## REGLAS DE COMPORTAMIENTO — NUNCA IGNORAR
1. Basa SIEMPRE tus recomendaciones en los datos reales del atleta mostrados arriba. Nunca des planes genéricos.
2. Si TSB < -20: prioriza recuperación y advierte explícitamente antes de proponer intensidad.
3. Si TSB > +15 y CTL es alto: el atleta está fresco y puede tolerar trabajo de calidad.
4. Si la semana previa tiene >10% más carga que el promedio de las últimas 4: advierte riesgo de sobrecarga.
5. Sesiones de entrenamiento deben incluir: duración total, zonas trabajadas, TSS estimado, calentamiento, bloque principal, vuelta a la calma.
6. Planes de gimnasio deben ser específicos para ciclismo (fuerza funcional, no hipertrofia). Incluir: ejercicio, series × reps, RIR o % 1RM, tempo de ejecución.
7. Nutrición: calcular según volumen real de entrenamiento. Diferenciar días de alto/bajo entrenamiento.
8. Si el usuario reporta fatiga inusual, dolor, o malestar → priorizar recuperación y sugerir descanso antes de entrenar.
9. No opines sobre temas fuera del deporte. Redirige amablemente.
10. Cuando generes un plan estructurado, usa formato de tabla markdown.`
}
```

---

## Lógica de Métricas Strava

```typescript
// lib/strava/metrics.ts

/**
 * Calcula FTP estimado desde actividades recientes.
 * Método: mayor esfuerzo normalizado sostenido ~20min × 0.95
 */
export function estimateFTP(activities: Activity[]): number { ... }

/**
 * Calcula CTL, ATL y TSB usando modelo PMC estándar.
 * CTL: media móvil exponencial de 42 días del TSS diario
 * ATL: media móvil exponencial de 7 días del TSS diario
 * TSB: CTL - ATL (día anterior)
 */
export function calculatePMC(activities: Activity[]): { ctl: number, atl: number, tsb: number } { ... }

/**
 * Calcula TSS de una actividad.
 * TSS = (duración_s × NP × IF) / (FTP × 3600) × 100
 * IF = NP / FTP
 */
export function calculateTSS(activity: Activity, ftp: number): number { ... }

/**
 * Determina distribución de tiempo por zonas de potencia (7 zonas Coggan).
 */
export function calculateZoneDistribution(streams: PowerStream, ftp: number): ZoneDistribution { ... }
```

---

## Tool Calls de la IA

Definir en `lib/ai/tools.ts`:

```typescript
export const chatTools: Tool[] = [
  {
    name: 'get_recent_activities',
    description: 'Obtiene actividades recientes del usuario desde Strava para análisis detallado',
    input_schema: {
      type: 'object',
      properties: {
        days: { type: 'number', description: 'Número de días hacia atrás (max 90)' },
        type: { type: 'string', description: 'Filtro por tipo: Ride, VirtualRide, WeightTraining' }
      }
    }
  },
  {
    name: 'save_training_plan',
    description: 'Guarda un plan de entrenamiento generado en el perfil del usuario',
    input_schema: {
      type: 'object',
      required: ['title', 'type', 'duration_weeks', 'content'],
      properties: {
        title: { type: 'string' },
        type: { type: 'string', enum: ['training', 'gym', 'nutrition', 'combined'] },
        duration_weeks: { type: 'number' },
        content: { type: 'object' }
      }
    }
  },
  {
    name: 'calculate_nutrition_targets',
    description: 'Calcula objetivos nutricionales personalizados según volumen de entrenamiento',
    input_schema: {
      type: 'object',
      required: ['training_hours_this_week'],
      properties: {
        training_hours_this_week: { type: 'number' },
        body_weight_kg: { type: 'number' },
        goal: { type: 'string', enum: ['performance', 'weight_loss', 'maintenance'] }
      }
    }
  },
  {
    name: 'trigger_strava_sync',
    description: 'Fuerza una sincronización con Strava para obtener datos más recientes',
    input_schema: { type: 'object', properties: {} }
  }
]
```

---

## Onboarding Conversacional

El onboarding es un chat especial (página separada `/onboarding`) que hace exactamente estas 6 preguntas en orden, guardando la respuesta de cada una antes de continuar.

```typescript
export const ONBOARDING_FLOW = [
  {
    id: 'objective',
    question: '¡Hola! Soy CycloAI, tu entrenador personal de ciclismo. Para empezar, ¿cuál es tu principal objetivo ahora mismo?',
    options: [
      { value: 'gran_fondo', label: 'Prepararme para una gran fondo o cicloturista' },
      { value: 'ftp_improvement', label: 'Mejorar mi FTP y potencia general' },
      { value: 'weight_loss', label: 'Perder peso sin perder rendimiento' },
      { value: 'climbing', label: 'Mejorar en subidas (W/kg)' },
      { value: 'category_upgrade', label: 'Subir de categoría amateur' },
    ]
  },
  {
    id: 'weekly_hours',
    question: '¿Cuántas horas a la semana puedes dedicar a entrenar? (bici + gimnasio en total)',
    type: 'number_select',
    options: ['4-6h', '6-8h', '8-10h', '10-12h', 'Más de 12h']
  },
  {
    id: 'gym_days',
    question: '¿Tienes acceso a gimnasio? ¿Cuántos días a la semana podrías ir?',
    options: ['No tengo acceso a gimnasio', '1 día', '2 días', '3 días']
  },
  {
    id: 'injuries',
    question: '¿Tienes alguna lesión actual, zona de dolor recurrente, o algo que debamos tener en cuenta?',
    type: 'free_text',
    placeholder: 'Ej: Rodilla derecha, lumbar, ninguna...'
  },
  {
    id: 'power_meter',
    question: '¿Entrenas con medidor de potencia? Si es así, ¿sabes tu FTP aproximado?',
    options: [
      { value: 'power_yes_ftp', label: 'Sí, tengo potenciómetro y sé mi FTP' },
      { value: 'power_yes_no_ftp', label: 'Sí, tengo potenciómetro pero no sé mi FTP' },
      { value: 'power_no', label: 'No tengo potenciómetro' }
    ]
  },
  {
    id: 'target_event',
    question: '¿Tienes algún evento o carrera objetivo en los próximos meses? (Si no tienes, no pasa nada)',
    type: 'free_text',
    placeholder: 'Ej: La Quebrantahuesos en julio, L\'Étape en agosto...'
  }
]
```

---

## Specs por Feature

Antes de implementar cada feature, crea o verifica que existe el archivo correspondiente en `/specs/`:

### `/specs/auth.md`
- **Login** (`/login`): formulario email + contraseña + botón "Continuar con Google"
- **Registro** (`/register`): formulario nombre + email + contraseña + botón "Registrarse con Google"
- Ambas páginas comparten el mismo estilo visual (ver `design.md` → sección "Auth Pages")
- Google OAuth gestionado íntegramente por Supabase Auth (proveedor Google habilitado en dashboard Supabase)
- Strava **NO** es proveedor de autenticación — es una integración posterior desde el perfil
- Tras login/registro exitoso → redirect a `/onboarding` si `onboarding_completed = false`, sino `/chat`
- Manejo de errores inline (no alerts del navegador): credenciales incorrectas, email ya registrado, etc.
- Link "¿Ya tienes cuenta? Inicia sesión" en `/register` y viceversa en `/login`
- Link "¿Olvidaste tu contraseña?" en `/login` → flujo de reset de Supabase Auth

### `/specs/profile.md`
Ruta: `/profile` (autenticado)  
Archivo: `app/(app)/profile/page.tsx`

Secciones de la página:

**1. Datos personales**
- Nombre, email (readonly si viene de Google), foto de perfil
- Botón "Guardar cambios" → actualiza tabla `profiles`

**2. Conexiones** ← sección clave
- Tarjeta Strava con estado visual claro:
  - **No conectado**: logo Strava + texto explicativo de por qué es importante + botón "Conectar Strava"
  - **Conectado**: logo Strava + nombre del atleta en Strava + fecha de conexión + botón "Desconectar" (destructivo, con confirm dialog)
- El botón "Conectar Strava" llama a `/api/strava/connect` que inicia el flujo OAuth de Strava
- El callback `/api/strava/callback` guarda los tokens en `strava_tokens` y actualiza `strava_connected = true` en `profiles`
- Tras conectar exitosamente → trigger automático de sync inicial (últimas 8 semanas)
- Texto bajo la tarjeta cuando no está conectado: "Conecta Strava para que CycloAI analice tu estado de forma real, calcule tu FTP y adapte cada entrenamiento a tu carga actual."

**3. Plan activo** (si existe)
- Resumen del plan de entrenamiento activo con botón para ir a `/plans`

**4. Cuenta**
- Botón "Cerrar sesión"
- Botón "Eliminar cuenta" (destructivo, con confirm dialog)

Componente Strava: `components/profile/StravaConnect.tsx`

### `/specs/onboarding.md`
- Flujo de 6 preguntas secuenciales
- Cada respuesta se guarda inmediatamente (no al final)
- Si el usuario cierra a mitad → retoma donde dejó en el próximo login
- Al completar → redirect a `/chat` (el sync de Strava es independiente y ocurre cuando el usuario conecta Strava desde `/profile`)
- Si Strava ya está conectado en el momento de completar el onboarding → trigger de sync en ese momento
- UI: ver `design.md` → sección "Onboarding Chat Flow"

### `/specs/strava-sync.md`
- El sync solo ocurre si `strava_connected = true` en el perfil del usuario
- Sync inicial: se dispara al conectar Strava desde `/profile` → últimas 8 semanas
- Sync incremental: solo actividades nuevas desde `last_sync_at`
- Webhook: recibir nuevas actividades en tiempo real
- Calcular y cachear en `profiles`: FTP, CTL, ATL, TSB, volumen, distribución zonas
- Rate limits: máx 100 req/15min, 1000 req/día
- Si el usuario no tiene Strava conectado → el system prompt lo indica y la IA invita a conectarlo desde `/profile`

### `/specs/chat-interface.md`
- Streaming de respuestas (no esperar a que termine)
- Render especial para tablas de planes (componente `TrainingPlanTable`)
- Render especial para tarjetas de métricas inline
- Botón "Guardar plan" cuando la IA genera uno
- Historial de conversaciones en sidebar
- UI: ver `design.md` → sección "Chat Interface"

### `/specs/ai-engine.md`
- System prompt dinámico con todos los datos del usuario
- RAG: top-4 chunks más relevantes por mensaje
- Tool calls: get_activities, save_plan, calculate_nutrition, trigger_sync
- Historial: últimos 20 mensajes en contexto
- Memoria persistente: últimos planes activos inyectados en system prompt
- Modelo: gemini-3.5-flash (via @ai-sdk/google)

### `/specs/rag-system.md`
- Ver archivo separado `RAG_GUIDE.md` para implementación completa

### `/specs/landing.md`
- Ver sección "Landing Page" más abajo en este archivo para spec completa

### `/specs/dashboard.md`
- Gráfico CTL/ATL/TSB últimos 90 días
- Distribución de zonas últimas 4 semanas (pie chart)
- Resumen semanal: km, horas, TSS, elevación
- Últimas 5 actividades con resumen
- UI: ver `design.md` → sección "Dashboard"

---

## Landing Page — Spec Completa

Ruta: `/` (página pública, sin autenticación)  
Archivo: `app/(marketing)/page.tsx`  
Layout compartido: `app/(marketing)/layout.tsx`  
Componentes: `components/landing/`

**SIEMPRE** consultar `design.md` para fuentes, colores, espaciados y tokens antes de implementar cualquier sección.  
La landing usa el mismo design system que la app — no crear variables de color ni tipografías nuevas.

---

### Navbar — `components/landing/Navbar.tsx`

Comportamiento:
- Fijo en la parte superior (`sticky top-0`) con blur de fondo al hacer scroll (`backdrop-blur`)
- Logo CycloAI a la izquierda (texto o SVG — ver `design.md`)
- Links de navegación en el centro: "Funcionalidades", "Precios" (scroll suave a las secciones con `#id`)
- Botones a la derecha: "Iniciar sesión" (variante ghost/outline) + "Empezar gratis" (variante primary/filled)
- En mobile: menú hamburguesa que despliega los links y botones en un panel vertical
- "Iniciar sesión" → href `/login`
- "Empezar gratis" → href `/login` (mismo destino, distinto estilo visual — convierte más)

```tsx
// Estructura JSX esperada
<nav>
  <Logo />
  <NavLinks>
    <a href="#funcionalidades">Funcionalidades</a>
    <a href="#precios">Precios</a>
  </NavLinks>
  <NavActions>
    <Button variant="ghost" href="/login">Iniciar sesión</Button>
    <Button variant="primary" href="/login">Empezar gratis</Button>
  </NavActions>
</nav>
```

---

### Hero Section — `components/landing/HeroSection.tsx`

Objetivo: comunicar la propuesta de valor en menos de 5 segundos.

Contenido:
- **Eyebrow** (texto pequeño sobre el headline): "Entrenamiento inteligente para ciclistas"
- **Headline** (H1, tamaño grande): "Tu entrenador personal de ciclismo, potenciado por IA"
- **Subheadline**: "Conecta Strava, responde 6 preguntas y obtén planes de entrenamiento, gimnasio y nutrición adaptados a tu estado de forma real. Sin planes genéricos."
- **CTA primario**: botón "Empezar gratis con Strava" → `/login`
- **CTA secundario** (opcional, texto link): "Ver cómo funciona" → scroll suave a `#funcionalidades`
- **Imagen/visual**: mockup del chat en acción (screenshot o ilustración del chat — ver `design.md` si hay asset definido; si no, usar un placeholder con clase `bg-muted` hasta tenerlo)
- Layout: dos columnas en desktop (texto izquierda, visual derecha), apilado en mobile

---

### Features Section — `components/landing/FeaturesSection.tsx`

ID de sección: `id="funcionalidades"`

Título de sección: "Todo lo que necesitas para rendir al máximo"

6 features en grid (3×2 desktop, 2×3 tablet, 1×6 mobile), cada una con:
- Icono (Lucide React o SVG simple)
- Título corto (3-5 palabras)
- Descripción (1-2 frases)

```
Feature 1 — "Conectado a tu Strava"
Sincroniza automáticamente tus actividades. Conocemos tu FTP, tu fatiga 
y tu forma actual antes de darte cualquier consejo.

Feature 2 — "Planes que se adaptan a ti"
No hay plantillas. Cada sesión, cada semana, cada bloque se construye 
sobre tus datos reales: potencia, volumen, consistencia.

Feature 3 — "Gimnasio aplicado al ciclismo"
Ejercicios de fuerza, core y movilidad específicos para mejorar en la 
bici. Nada de rutinas de culturismo.

Feature 4 — "Nutrición por volumen de carga"
Los macros cambian cada semana según cuánto entrenas. Días duros, días 
suaves, cargas, competición — todo calculado.

Feature 5 — "Chat en tiempo real"
Pregunta lo que quieras: una sesión para mañana, qué comer antes de 
una gran fondo, por qué te duelen las rodillas. Respuesta inmediata.

Feature 6 — "Basado en ciencia"
Periodización polarizada, modelo PMC, zonas de potencia Coggan, 
protocolos validados. No bro-science.
```

---

### Pricing Section — `components/landing/PricingSection.tsx`

ID de sección: `id="precios"`

Título: "Empieza gratis. Escala cuando lo necesites."

3 tarjetas en row desktop, apiladas en mobile. La tarjeta Pro debe destacar visualmente (borde o fondo diferenciado — ver `design.md` para el tratamiento de "destacado").

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│      FREE       │  │   PRO ⭐         │  │    PREMIUM      │
│     0 €/mes     │  │   9,99 €/mes    │  │  19,99 €/mes    │
│─────────────────│  │─────────────────│  │─────────────────│
│ 20 mensajes/mes │  │ Mensajes ilimit.│  │ Todo de Pro +   │
│ Onboarding      │  │ Sync Strava     │  │ Exportar PDF    │
│ 1 plan guardado │  │ Planes ilimit.  │  │ Análisis avanz. │
│                 │  │ Nutrición       │  │ Soporte prior.  │
│                 │  │ Dashboard CTL   │  │                 │
│─────────────────│  │─────────────────│  │─────────────────│
│  [Empezar gratis]│  │[Empezar con Pro]│  │ [Empezar Premium│
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

Todos los botones → `/login`

Nota bajo las tarjetas: "Sin permanencia. Cancela cuando quieras."

---

### CTA Section — `components/landing/CtaSection.tsx`

Sección final antes del footer. Fondo diferenciado (color de acento o degradado — ver `design.md`).

Contenido:
- **Headline**: "¿Listo para entrenar con datos reales?"
- **Subtext**: "Conecta Strava en 30 segundos y empieza hoy."
- **Botón**: "Empezar gratis" → `/login`

Layout centrado, sin distracciones.

---

### Footer — `components/landing/Footer.tsx`

Simple y limpio. 3 columnas desktop, apilado mobile:

```
Columna 1 — Marca
  Logo + tagline corto
  "© 2026 CycloAI"

Columna 2 — Producto
  Funcionalidades
  Precios
  Changelog (puede ser un href vacío "#" de momento)

Columna 3 — Legal / Soporte
  Política de privacidad  (href "#" de momento)
  Términos de uso         (href "#" de momento)
  Contacto                (href "#" de momento)
```

Sin exceso de links. El footer no es el lugar para convertir.

---

### Layout de la landing — `app/(marketing)/layout.tsx`

```tsx
export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Navbar />
      <main>{children}</main>
      <Footer />
    </>
  )
}
```

---

### Acceptance Criteria de la Landing

- [ ] Navbar sticky funciona en scroll, con efecto blur
- [ ] Links de navbar hacen scroll suave a las secciones correctas
- [ ] "Iniciar sesión" y "Empezar gratis" llevan a `/login`
- [ ] Hero visible completo en viewport de 1280×800 sin scroll
- [ ] 6 features en grid responsive (3-2-1 columnas)
- [ ] Pricing: tarjeta Pro visualmente destacada respecto a las otras
- [ ] Todos los botones de pricing llevan a `/login`
- [ ] Footer con 3 columnas en desktop, apilado en mobile ≤768px
- [ ] Ningún color, fuente o espaciado que no esté en `design.md`
- [ ] Lighthouse Performance ≥ 90 en desktop
- [ ] No hay errores de hidratación SSR

---

## UI — Reglas Importantes

**SIEMPRE** consultar `design.md` antes de crear cualquier componente visual. Las reglas son:

1. No importar librerías de UI externas (shadcn, MUI, etc.) sin que estén especificadas en `design.md`
2. Los colores, tipografías y espaciados vienen de los tokens en `design.md`
3. La interfaz de chat debe replicar fielmente el estilo definido en `design.md`
4. Los componentes reutilizables van en `/components/ui/` y deben estar documentados

---

## Testing

```bash
# Unit tests
pnpm vitest

# E2E
pnpm playwright test

# Type check
pnpm tsc --noEmit
```

Cada feature debe tener al menos:
- Tests unitarios para lógica de negocio (métricas, system prompt builder, RAG)
- Test E2E para flujos críticos (login, onboarding, enviar mensaje)

---

## Comandos de Desarrollo

```bash
pnpm dev              # Servidor de desarrollo
pnpm build            # Build de producción
pnpm db:migrate       # Ejecutar migraciones Supabase
pnpm db:seed          # Seed de knowledge base en pgvector
pnpm strava:webhook   # Registrar webhook de Strava
pnpm rag:index        # Indexar/reindexar knowledge base
```

---

## Notas para Claude Code

- Ante cualquier duda sobre UI: leer `design.md` antes de preguntar
- Ante cualquier duda sobre el sistema RAG: leer `RAG_GUIDE.md`
- Registrar en engram toda decisión técnica no especificada aquí
- Usar gentle-ai para razonar en voz alta antes de implementar lógica compleja
- El archivo más crítico es `app/api/chat/route.ts` + `lib/ai/system-prompt.ts` — aquí vive el valor diferencial del producto
- Prioridad de implementación: Auth → Onboarding → Strava Sync → Chat básico → RAG → Dashboard
