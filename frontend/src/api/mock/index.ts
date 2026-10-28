import { ApiClient, type ApiClientOptions } from "../client";
import { MockTransport, type MockTransportOptions } from "./mockTransport";

export { MockTransport } from "./mockTransport";
export type { MockTransportOptions } from "./mockTransport";
export { SCENARIO_NAMES, isScenarioName, type ScenarioName } from "./scenarios";
export { MOCK_ACCOUNTS, MOCK_PUBLIC_SLUG, MOCK_LIMITS, IDS as MOCK_IDS } from "./fixtures";

/** ApiClient on a fresh MockTransport (`VITE_API_MOCK=1`, 06 section 6.2). */
export function createMockClient(
  opts: MockTransportOptions & ApiClientOptions = {},
): ApiClient {
  const { scenario, latencyMs, ...clientOpts } = opts;
  return new ApiClient(new MockTransport({ scenario, latencyMs }), clientOpts);
}
