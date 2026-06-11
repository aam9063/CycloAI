interface StravaConnectProps {
  connected: boolean | null;
  connectedAt: string | null;
}

function formatDate(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Intl.DateTimeFormat("es-ES", {
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export default function StravaConnect({
  connected,
  connectedAt,
}: StravaConnectProps) {
  if (connected === true) {
    // Connected state — authored for strava-sync landing.
    // This branch is currently unreachable (strava_connected is false/null for all users).
    // The strava-sync change will flip the data path without re-authoring this structure.
    return (
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <span className="font-semibold text-ink text-[15px]">Strava</span>
          <span className="text-[13px] text-ink-mute">
            Conectado el {formatDate(connectedAt)}
          </span>
        </div>

        {/* Desconectar — placeholder; no handler until strava-sync lands */}
        <button
          type="button"
          disabled
          aria-disabled="true"
          className="inline-flex items-center justify-center font-medium text-[14px] leading-none rounded-sm px-4 py-2 min-h-[44px] bg-canvas border border-hairline-strong text-ink-mute cursor-not-allowed opacity-60 w-fit"
        >
          Desconectar
        </button>
      </div>
    );
  }

  // Disconnected state (the live branch for the current ship)
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <span className="font-semibold text-ink text-[15px]">Strava</span>
        <p className="text-[14px] text-ink-mute leading-[1.5]">
          Conecta Strava para que CycloAI analice tu estado de forma real,
          calcule tu FTP y adapte cada entrenamiento a tu carga actual.
        </p>
      </div>

      {/* Native <button> — NOT a Link — so the disabled attribute is honored by the browser */}
      <div className="flex flex-col gap-1 items-start">
        <button
          type="button"
          disabled
          aria-disabled="true"
          className="inline-flex items-center justify-center font-medium text-[14px] leading-none rounded-sm px-4 py-2 min-h-[44px] bg-canvas border border-hairline-strong text-ink opacity-60 cursor-not-allowed pointer-events-none"
        >
          Conectar Strava
        </button>
        <p className="text-[13px] text-ink-mute">Disponible próximamente</p>
      </div>
    </div>
  );
}
