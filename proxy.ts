import { updateSession } from "@/lib/supabase/middleware";
import type { NextRequest } from "next/server";

export async function proxy(request: NextRequest) {
  return updateSession(request);
}

export const config = {
  matcher: [
    /*
     * Run proxy on all paths EXCEPT:
     *   - _next/static  (static assets)
     *   - _next/image   (image optimization)
     *   - favicon.ico
     *   - auth/callback (CRITICAL: must be excluded to avoid redirect loop)
     *   - files with a known static extension (svg, png, jpg, etc.)
     */
    "/((?!_next/static|_next/image|favicon\\.ico|auth/callback|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
