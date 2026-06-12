import { redirect } from "next/navigation";

// WAITLIST MODE: /register is closed — bounce to the waitlist.
// Remove this file and restore the form to re-open registrations.
export default function RegisterPage() {
  redirect("/#waitlist");
}
