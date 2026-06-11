'use client';

interface SuggestionChipsProps {
  onSelect: (text: string) => void;
  disabled?: boolean;
}

const CHIPS = [
  '¿Qué entrenamiento me recomiendas esta semana?',
  'Dame un plan de gimnasio para ciclistas',
  '¿Cómo puedo mejorar mi FTP?',
  '¿Qué debo comer antes de una salida larga?',
] as const;

/**
 * Static suggestion chips shown in the welcome / zero-messages state.
 * Each chip is a native <button> for full keyboard operability.
 */
export default function SuggestionChips({ onSelect, disabled }: SuggestionChipsProps) {
  return (
    <div
      className="flex flex-wrap gap-2 justify-center"
      role="group"
      aria-label="Preguntas sugeridas"
    >
      {CHIPS.map((chip) => (
        <button
          key={chip}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(chip)}
          className={[
            'min-h-[44px] px-4 py-2 rounded-full text-[14px] leading-[1.4]',
            'border border-hairline bg-canvas text-ink',
            'hover:bg-canvas-soft hover:border-hairline-strong',
            'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
            'transition-colors duration-150',
            'disabled:opacity-50 disabled:cursor-not-allowed',
          ].join(' ')}
        >
          {chip}
        </button>
      ))}
    </div>
  );
}
