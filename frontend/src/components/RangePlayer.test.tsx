import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RangePlayer } from "./RangePlayer";
import {
  fakeVideo,
  installFakeVideo,
  playThrough,
  seekTo,
  tick,
} from "./testing/fakeVideo";

beforeEach(() => {
  installFakeVideo();
  fakeVideo.reset();
});

function video(container: HTMLElement): HTMLVideoElement {
  const v = container.querySelector("video");
  if (!v) throw new Error("no <video>");
  return v;
}

function mount(
  props: Partial<React.ComponentProps<typeof RangePlayer>> = {},
) {
  const onRangeComplete = vi.fn();
  const utils = render(
    <RangePlayer
      src="/media/clip-a.mp4"
      captionsSrc="/media/clip-a.vtt"
      startS={12}
      endS={21}
      autoplay={false}
      onRangeComplete={onRangeComplete}
      {...props}
    />,
  );
  const v = video(utils.container);
  return { ...utils, v, onRangeComplete };
}

describe("FE-PLY RangePlayer", () => {
  it("FE-PLY-01 start position and attributes", () => {
    const { v } = mount();
    expect(v.getAttribute("playsinline")).not.toBeNull();
    expect(v.getAttribute("preload")).toBe("metadata");
    expect(v.hasAttribute("controls")).toBe(false);
    fireEvent.loadedMetadata(v);
    expect(v.currentTime).toBe(12);
  });

  it("FE-PLY-02 stops at the range end and reports once", () => {
    const { v, onRangeComplete } = mount();
    fireEvent.loadedMetadata(v);
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    fakeVideo.pause.mockClear();
    playThrough(v, 12, 21);
    // Extra events after the pause (browsers fire them) change nothing.
    tick(v, 21);
    tick(v, 21);
    expect(fakeVideo.pause).toHaveBeenCalledTimes(1);
    expect(onRangeComplete).toHaveBeenCalledTimes(1);
    const arg = onRangeComplete.mock.calls[0]![0];
    expect(arg.positionS).toBeCloseTo(21, 1);
    expect(arg.watchedS).toBeCloseTo(9, 1);
  });

  it("FE-PLY-02 stops at the end even when the range is not complete", () => {
    const { v, onRangeComplete } = mount();
    fireEvent.loadedMetadata(v);
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    fakeVideo.pause.mockClear();
    tick(v, 21.1);
    expect(fakeVideo.pause).toHaveBeenCalledTimes(1);
    expect(v.currentTime).toBe(21);
    expect(onRangeComplete).not.toHaveBeenCalled();
  });

  it("FE-PLY-03 seeking outside the range snaps back, no completion", () => {
    const { v, onRangeComplete } = mount();
    fireEvent.loadedMetadata(v);
    seekTo(v, 5);
    expect(v.currentTime).toBe(12);
    seekTo(v, 40);
    expect(v.currentTime).toBe(21);
    tick(v, 21);
    expect(onRangeComplete).not.toHaveBeenCalled();
  });

  it("FE-PLY-03 a seek inside the range is allowed", () => {
    const { v } = mount();
    fireEvent.loadedMetadata(v);
    seekTo(v, 15);
    expect(v.currentTime).toBe(15);
  });

  it("FE-PLY-04 captions track only when the URL is given", () => {
    const first = mount();
    const track = first.container.querySelector("track");
    expect(track).not.toBeNull();
    expect(track!.getAttribute("kind")).toBe("captions");
    expect(track!.getAttribute("src")).toBe("/media/clip-a.vtt");
    expect(screen.getByRole("button", { name: "Captions" })).toBeInTheDocument();
    first.unmount();

    const second = mount({ captionsSrc: undefined });
    expect(second.container.querySelector("track")).toBeNull();
  });

  it("FE-PLY-05 one player at a time", () => {
    const a = render(
      <RangePlayer
        src="/media/a.mp4"
        startS={2}
        endS={9}
        autoplay={false}
        onRangeComplete={vi.fn()}
      />,
    );
    const b = render(
      <RangePlayer
        src="/media/b.mp4"
        startS={30}
        endS={38}
        autoplay={false}
        onRangeComplete={vi.fn()}
      />,
    );
    const va = video(a.container);
    const vb = video(b.container);
    fireEvent.loadedMetadata(va);
    fireEvent.loadedMetadata(vb);
    fireEvent.click(within(a.container).getByRole("button", { name: "Play" }));
    expect(va.paused).toBe(false);
    fireEvent.click(within(b.container).getByRole("button", { name: "Play" }));
    expect(va.paused).toBe(true);
    expect(vb.paused).toBe(false);
    expect(vb.currentTime).toBe(30);
  });

  it("FE-PLY-06 URLs are used exactly as served", () => {
    const withCaps = mount({
      src: "/media/abc.mp4?sig=1",
      captionsSrc: "/media/xyz.vtt",
    });
    expect(withCaps.v.getAttribute("src")).toBe("/media/abc.mp4?sig=1");
    expect(withCaps.container.querySelector("track")!.getAttribute("src")).toBe(
      "/media/xyz.vtt",
    );
    withCaps.unmount();

    const noCaps = mount({ src: "/media/q.mp4", captionsSrc: null });
    expect(noCaps.v.getAttribute("src")).toBe("/media/q.mp4");
    expect(noCaps.container.querySelector("track")).toBeNull();
    expect(screen.queryByRole("button", { name: "Captions" })).toBeNull();
    expect(screen.getByText("No captions for this clip.")).toBeInTheDocument();
  });

  it("Play stays disabled until metadata has loaded (P1)", () => {
    const { v } = mount();
    expect(screen.getByRole("button", { name: /Play|Loading clip/ })).toBeDisabled();
    fireEvent.loadedMetadata(v);
    expect(screen.getByRole("button", { name: "Play" })).toBeEnabled();
  });

  it("Play after the end seeks back to the start (P2)", () => {
    const { v } = mount();
    fireEvent.loadedMetadata(v);
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    playThrough(v, 12, 21);
    fireEvent.click(screen.getByRole("button", { name: "Replay" }));
    expect(v.currentTime).toBe(12);
  });
});
