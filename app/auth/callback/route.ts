import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");

  // If there is no code, something went wrong before we got here.
  if (!code) {
    return NextResponse.redirect(`${origin}/login`);
  }

  const supabase = await createClient();

  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    return NextResponse.redirect(
      `${origin}/login?error=auth_callback_failed`
    );
  }

  // Determine where to send the user after a successful OAuth sign-in.
  // Treat a missing or null onboarding_completed as false (trigger may not
  // have fired yet — race window is narrow but must be handled).
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (user) {
    const { data: profile } = await supabase
      .from("profiles")
      .select("onboarding_completed")
      .eq("id", user.id)
      .single();

    if (!profile?.onboarding_completed) {
      return NextResponse.redirect(`${origin}/onboarding`);
    }

    return NextResponse.redirect(`${origin}/chat`);
  }

  // Fallback — should not normally be reached after a successful exchange.
  return NextResponse.redirect(`${origin}/login`);
}
