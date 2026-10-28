import { useCallback, useEffect, useRef, useState } from "react";
import { RangeTracker, type RangeReport } from "./RangeTracker";
import { formatClock } from "../lib/time";

export interface RangePlayerProps {
  /** `media_url` exactly as the API served it (D7). Never built from a clip id. */
  src: string;
  /** `captions_url` as served; absent or null means no track and no button. */
  captionsSrc?: string | null;
  startS: number;
  endS: number;
  autoplay?: boolean;
  /** Once per play-through, when the tracker says the range is complete. */
  onRangeComplete?: (report: RangeReport) => void;
  onProgress?: (positionS: number) => void;
}

/** Every mounted player, so starting one pauses the others (05 P12). */
const players = new Set<HTMLVideoElement>();

const EDGE_S = 0.25;

/**
 * Video element for one evidence range (05 section 4, 06 section 6.3). Own
 * controls only: the native scrubber could leave the range.
 */
export function RangePlayer({
  src,
  captionsSrc,
  startS,
  endS,
  autoplay = false,
  onRangeComplete,
  onProgress,
}: RangePlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const tracker = useRef<RangeTracker>(new RangeTracker(startS, endS));
  const stopped = useRef(false);
  const raf = useRef<number | null>(null);
  const cb = useRef({ onRangeComplete, onProgress });
  cb.current = { onRangeComplete, onProgress };

  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [finished, setFinished] = useState(false);
  const [position, setPosition] = useState(startS);
  const [captionsOn, setCaptionsOn] = useState(true);
  const [muted, setMuted] = useState(false);

  // A new range or source starts a new tracker.
  useEffect(() => {
    tracker.current = new RangeTracker(startS, endS);
    stopped.current = false;
    setReady(false);
    setPlaying(false);
    setFinished(false);
    setPosition(startS);
  }, [src, startS, endS]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    players.add(v);
    return () => {
      players.delete(v);
    };
  }, []);

  const handleSample = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    const t = v.currentTime;
    const tr = tracker.current;
    tr.onTimeUpdate(t);
    setPosition(Math.min(Math.max(t, startS), endS));
    cb.current.onProgress?.(t);
    if (t >= endS && !stopped.current) {
      stopped.current = true;
      v.pause();
      v.currentTime = endS;
      tr.onTimeUpdate(endS);
      setFinished(true);
      const done = tr.takeCompletion();
      if (done) cb.current.onRangeComplete?.(done);
    }
  }, [startS, endS]);

  // Frame-level stop check while playing (05 P3); timeupdate is the backup.
  useEffect(() => {
    if (!playing || typeof requestAnimationFrame !== "function") return;
    const loop = () => {
      handleSample();
      raf.current = requestAnimationFrame(loop);
    };
    raf.current = requestAnimationFrame(loop);
    return () => {
      if (raf.current !== null) cancelAnimationFrame(raf.current);
      raf.current = null;
    };
  }, [playing, handleSample]);

  useEffect(() => {
    const onHidden = () => {
      if (document.visibilityState === "hidden") {
        videoRef.current?.pause();
      }
    };
    document.addEventListener("visibilitychange", onHidden);
    return () => document.removeEventListener("visibilitychange", onHidden);
  }, []);

  const clampSeek = () => {
    const v = videoRef.current;
    if (!v) return;
    const t = v.currentTime;
    let target = t;
    if (t < startS - 0.05) target = startS;
    else if (t > endS + 0.05) target = endS;
    if (target !== t) v.currentTime = target;
    tracker.current.onSeek(target);
    if (target < endS) stopped.current = false;
    setFinished(false);
    setPosition(target);
  };

  const onLoadedMetadata = () => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = startS;
    setReady(true);
    if (autoplay) void v.play();
  };

  const onPlay = () => {
    const me = videoRef.current;
    for (const other of players) {
      if (other !== me && !other.paused) other.pause();
    }
    stopped.current = false;
    setPlaying(true);
  };

  const onPause = () => {
    tracker.current.onPause();
    setPlaying(false);
  };

  const press = () => {
    const v = videoRef.current;
    if (!v || !ready) return;
    if (!v.paused) {
      v.pause();
      return;
    }
    if (v.currentTime < startS - EDGE_S || v.currentTime >= endS - 0.05) {
      if (finished) tracker.current.rearm();
      v.currentTime = startS;
      tracker.current.onSeek(startS);
      setFinished(false);
      setPosition(startS);
    }
    stopped.current = false;
    void v.play();
  };

  const toggleCaptions = () => {
    const next = !captionsOn;
    setCaptionsOn(next);
    const tracks = videoRef.current?.textTracks;
    if (tracks) {
      for (let i = 0; i < tracks.length; i++) {
        tracks[i].mode = next ? "showing" : "hidden";
      }
    }
  };

  const toggleSound = () => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = !muted;
    setMuted(!muted);
  };

  const onSlider = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = videoRef.current;
    if (!v) return;
    const t = Math.min(Math.max(Number(e.target.value), startS), endS);
    v.currentTime = t;
    tracker.current.onSeek(t);
    setPosition(t);
  };

  const hasCaptions = Boolean(captionsSrc);
  const playLabel = !ready ? "Loading clip" : finished ? "Replay" : playing ? "Pause" : "Play";

  return (
    <div className="range-player">
      <video
        ref={videoRef}
        src={src}
        playsInline
        preload="metadata"
        disablePictureInPicture
        controlsList="nodownload nofullscreen"
        onLoadedMetadata={onLoadedMetadata}
        onTimeUpdate={handleSample}
        onSeeking={clampSeek}
        onSeeked={clampSeek}
        onPlay={onPlay}
        onPause={onPause}
        onEnded={handleSample}
        onRateChange={(e) => {
          if (e.currentTarget.playbackRate !== 1) e.currentTarget.playbackRate = 1;
        }}
      >
        {hasCaptions && <track kind="captions" default src={captionsSrc ?? undefined} />}
      </video>
      <div className="range-player__controls">
        <button type="button" onClick={press} disabled={!ready}>
          {playLabel}
        </button>
        <input
          type="range"
          aria-label="Position"
          min={startS}
          max={endS}
          step={0.1}
          value={position}
          onChange={onSlider}
        />
        <span className="range-player__time">
          {formatClock(startS)} - {formatClock(endS)} ({formatClock(position)})
        </span>
        {hasCaptions ? (
          <button type="button" aria-pressed={captionsOn} onClick={toggleCaptions}>
            Captions
          </button>
        ) : (
          <span>No captions for this clip.</span>
        )}
        <button type="button" aria-pressed={!muted} onClick={toggleSound}>
          Sound
        </button>
      </div>
    </div>
  );
}
