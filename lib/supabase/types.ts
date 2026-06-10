// Hand-written minimal types — full codegen deferred until DB tooling is set up.

export interface Profile {
  id: string;
  display_name: string | null;
  avatar_url: string | null;
  onboarding_completed: boolean;
  // Onboarding fields
  objective: string | null;
  weekly_hours: number | null;
  gym_days_per_week: number | null;
  injuries: string | null;
  has_power_meter: boolean | null;
  ftp_estimated: number | null;
  target_event: string | null;
  target_event_date: string | null;
}
