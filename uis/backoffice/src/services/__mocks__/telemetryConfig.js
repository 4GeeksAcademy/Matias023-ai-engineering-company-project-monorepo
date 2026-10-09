/**
 * Manual mock for telemetryConfig — plain JS, no import.meta.
 * Jest resolves this via moduleNameMapper to avoid loading the real module
 * (which contains import.meta.env, unsupported under CommonJS).
 */
function getTelemetryEndpoint() {
  return null
}
module.exports = { getTelemetryEndpoint }