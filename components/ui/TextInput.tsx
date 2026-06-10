import { forwardRef } from "react";

interface TextInputProps {
  id: string;
  name: string;
  label: string;
  type?: "text" | "email" | "password";
  autoComplete?: string;
  required?: boolean;
  defaultValue?: string;
  /** When set, renders an inline error message and marks the input invalid. */
  error?: string | null;
  placeholder?: string;
}

const TextInput = forwardRef<HTMLInputElement, TextInputProps>(
  function TextInput(
    {
      id,
      name,
      label,
      type = "text",
      autoComplete,
      required,
      defaultValue,
      error,
      placeholder,
    },
    ref
  ) {
    const errorId = `${id}-error`;
    const hasError = Boolean(error);

    return (
      <div className="flex flex-col gap-1">
        <label
          htmlFor={id}
          className="text-[14px] font-medium text-ink leading-none"
        >
          {label}
        </label>

        <input
          ref={ref}
          id={id}
          name={name}
          type={type}
          autoComplete={autoComplete}
          required={required}
          defaultValue={defaultValue}
          placeholder={placeholder}
          aria-invalid={hasError ? "true" : undefined}
          aria-describedby={hasError ? errorId : undefined}
          className={[
            "w-full min-h-[44px] rounded-sm px-3 py-2",
            "bg-canvas text-ink text-[16px] leading-[1.5]",
            "placeholder:text-ink-faint",
            "border",
            hasError
              ? "border-hairline-strong"
              : "border-hairline",
            "focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink",
            "transition-colors",
          ]
            .join(" ")
            .trim()}
        />

        {hasError && (
          <p
            id={errorId}
            role="alert"
            aria-live="polite"
            className="text-[13px] text-ink-mute leading-[1.45]"
          >
            {error}
          </p>
        )}
      </div>
    );
  }
);

export default TextInput;
