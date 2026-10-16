import type { ActivityEvent } from "../api/types";

/** Stand-in for the browser's EventSource (jsdom has none). Tests push events with `emit`. */
export class MockEventSource {
  static instances: MockEventSource[] = [];
  static latest(): MockEventSource {
    return MockEventSource.instances[MockEventSource.instances.length - 1];
  }

  readyState = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((msg: { data: string }) => void) | null = null;

  constructor(readonly url: string) {
    MockEventSource.instances.push(this);
  }

  open() {
    this.readyState = 1;
    this.onopen?.();
  }

  emit(event: ActivityEvent) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }

  fail() {
    this.onerror?.();
  }

  close() {
    this.readyState = 2;
  }
}
