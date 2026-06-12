import 'server-only';

import { Ratelimit } from '@upstash/ratelimit';
import { Redis } from '@upstash/redis';
import { headers } from 'next/headers';

// ---------------------------------------------------------------------------
// Redis client — lazily initialised so build-time imports don't crash
// when env vars are absent.
// ---------------------------------------------------------------------------

let _redis: Redis | null = null;

function getRedis(): Redis | null {
  if (_redis) return _redis;

  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;

  if (!url || !token) return null;

  _redis = new Redis({ url, token });
  return _redis;
}

// ---------------------------------------------------------------------------
// Ratelimit instance cache — one instance per (limit, window) pair so we
// don't rebuild the sliding-window algorithm on every request.
// ---------------------------------------------------------------------------

const _limiterCache = new Map<string, Ratelimit>();

function getLimiter(limit: number, windowSeconds: number): Ratelimit | null {
  const redis = getRedis();
  if (!redis) return null;

  const cacheKey = `${limit}:${windowSeconds}`;
  const cached = _limiterCache.get(cacheKey);
  if (cached) return cached;

  const limiter = new Ratelimit({
    redis,
    limiter: Ratelimit.slidingWindow(limit, `${windowSeconds} s`),
    analytics: false,
  });

  _limiterCache.set(cacheKey, limiter);
  return limiter;
}

// ---------------------------------------------------------------------------
// Whether we've already warned about missing config in this process lifetime.
// ---------------------------------------------------------------------------
let _warnedUnconfigured = false;

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Reads the client IP from standard proxy headers.
 * Falls back to '127.0.0.1' when neither header is present (local dev).
 */
export async function getClientIp(): Promise<string> {
  const h = await headers();

  const forwarded = h.get('x-forwarded-for');
  if (forwarded) {
    // x-forwarded-for can be a comma-separated list; the first entry is the client.
    return forwarded.split(',')[0].trim();
  }

  const realIp = h.get('x-real-ip');
  if (realIp) return realIp.trim();

  return '127.0.0.1';
}

/**
 * Checks whether the given key is within its rate-limit budget.
 *
 * Behavior when Upstash is not configured:
 * - Development: returns { success: true, configured: false } and prints a
 *   one-time console.warn so local dev is never blocked.
 * - Production: also returns { success: true, configured: false } to avoid
 *   breaking the public form, BUT logs a loud console.error on every call.
 *   Provisioning Upstash is required for the protection to actually engage.
 */
export async function checkRateLimit(opts: {
  key: string;
  limit: number;
  windowSeconds: number;
}): Promise<{ success: boolean; configured: boolean }> {
  const limiter = getLimiter(opts.limit, opts.windowSeconds);

  if (!limiter) {
    // Upstash env vars are absent.
    if (process.env.NODE_ENV !== 'production') {
      if (!_warnedUnconfigured) {
        console.warn(
          '[ratelimit] Upstash not configured — rate limiting is INACTIVE in local dev. ' +
            'Set UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN to enable it.'
        );
        _warnedUnconfigured = true;
      }
    } else {
      // Production with missing config — loud error on every call.
      console.error(
        '[ratelimit] NOT CONFIGURED in production — waitlist/chat flood protection INACTIVE. ' +
          'Provision Upstash and set UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN immediately.'
      );
    }
    return { success: true, configured: false };
  }

  const { success } = await limiter.limit(opts.key);
  return { success, configured: true };
}
