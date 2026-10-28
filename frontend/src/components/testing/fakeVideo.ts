import { fireEvent } from "@testing-library/react";
import { vi } from "vitest";

/**
 * jsdom does not implement media playback. This installs a small fake on
 * HTMLMediaElement: per-element `currentTime`, `paused`, and `play`/`pause`
 * that fire the matching events, like a real element.
 */
interface State {
  t: number;
  paused: boolean;
}

const states = new WeakMap<HTMLMediaElement, State>();
const st = (el: HTMLMediaElement): State => {
  let s = states.get(el);
  if (!s) {
    s = { t: 0, paused: true };
    states.set(el, s);
  }
  return s;
};

export const fakeVideo = {
  play: vi.fn(),
  pause: vi.fn(),
  reset() {
    this.play.mockClear();
    this.pause.mockClear();
  },
};

export function installFakeVideo(): void {
  const proto = HTMLMediaElement.prototype;
  Object.defineProperty(proto, "currentTime", {
    configurable: true,
    get(this: HTMLMediaElement) {
      return st(this).t;
    },
    set(this: HTMLMediaElement, v: number) {
      st(this).t = v;
    },
  });
  Object.defineProperty(proto, "paused", {
    configurable: true,
    get(this: HTMLMediaElement) {
      return st(this).paused;
    },
  });
  Object.defineProperty(proto, "duration", {
    configurable: true,
    get: () => 120,
  });
  fakeVideo.play.mockImplementation(function (this: HTMLMediaElement) {
    st(this).paused = false;
    fireEvent(this, new Event("play"));
    return Promise.resolve();
  });
  fakeVideo.pause.mockImplementation(function (this: HTMLMediaElement) {
    if (st(this).paused) return;
    st(this).paused = true;
    fireEvent(this, new Event("pause"));
  });
  proto.play = fakeVideo.play as unknown as typeof proto.play;
  proto.pause = fakeVideo.pause as unknown as typeof proto.pause;
}

/** Set the playhead and fire the matching media event. */
export function tick(el: HTMLVideoElement, t: number): void {
  el.currentTime = t;
  fireEvent.timeUpdate(el);
}

/** Simulate a user seek: move the playhead, then `seeking`. */
export function seekTo(el: HTMLVideoElement, t: number): void {
  el.currentTime = t;
  fireEvent(el, new Event("seeking"));
  fireEvent(el, new Event("seeked"));
}

/** Play from a to b in 0.25 s steps through `timeupdate`. */
export function playThrough(
  el: HTMLVideoElement,
  a: number,
  b: number,
  step = 0.25,
): void {
  const n = Math.round((b - a) / step);
  for (let i = 0; i <= n; i++) tick(el, a + i * step);
}
