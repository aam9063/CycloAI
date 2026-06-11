// Hand-written minimal types — full codegen deferred until DB tooling is set up.

export interface Profile {
  id: string;
  created_at: string | null;
  updated_at: string | null;
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
  // Strava integration
  strava_id: number | null;
  strava_connected: boolean | null;
  strava_connected_at: string | null;
  // Strava metric cache
  ctl: number | null;
  atl: number | null;
  tsb: number | null;
  weekly_volume_km: number | null;
  weekly_volume_hours: number | null;
  avg_days_per_week: number | null;
  last_sync_at: string | null;
}
