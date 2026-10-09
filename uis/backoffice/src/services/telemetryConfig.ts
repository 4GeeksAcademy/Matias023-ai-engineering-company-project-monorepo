/**
 * Telemetry environment configuration.
 *
 * Vite replaces `import.meta.env.VITE_TELEMETRY_ENDPOINT` at build time
 * with the actual environment variable value. This module is the single
 * boundary for accessing that variable.
 *
 * In tests, mock this module with `jest.mock(...)` so ts-jest never needs
 * to parse `import.meta` under CommonJS.
 */
export function getTelemetryEndpoint(): string | null {
  // Vite statically replaces import.meta.env at build time — no eval, no trickery.
  const url = import.meta.env.VITE_TELEMETRY_ENDPOINT
  if (typeof url === 'string' && url.length > 0) return url
  return null
}