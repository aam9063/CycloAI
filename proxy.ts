import { sessionGate } from "@/lib/api/middleware";
import type { NextRequest } from "next/server";

export async function proxy(request: NextRequest) {
  return sessionGate(request);
}

export const config = {
  matcher: [
    /*
     * Run proxy on all paths EXCEPT:
     *   - _next/static  (static assets)
     *   - _next/image   (image optimization)
     *   - favicon.ico
     *   - files with a known static extension (svg, png, jpg, etc.)
     */
    "/((?!_next/static|_next/image|favicon\\.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
