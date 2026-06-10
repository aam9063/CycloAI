// Hand-written minimal types — full codegen deferred until DB tooling is set up.

export interface Profile {
  id: string;
  display_name: string | null;
  avatar_url: string | null;
  onboarding_completed: boolean;
}
