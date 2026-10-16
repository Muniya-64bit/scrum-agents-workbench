import "@testing-library/jest-dom/vitest";

import { MockEventSource } from "./eventSource";

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
});
