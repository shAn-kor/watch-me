import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Clip } from "../../api/types";
import { ClipRow, LocalRow } from "./ClipRows";

const LONG = `${"IMG_0414_very_long_clip_name_".repeat(6)}.MOV`;

function clip(over: Partial<Clip> = {}): Clip {
  return {
    id: "c1",
    session_id: "s1",
    ordinal: 1,
    original_filename: LONG,
    original_size_bytes: 1000,
    duration_s: 12,
    has_audio: true,
    status: "processing",
    step: "transcode",
    fail_code: null,
    error: null,
    media_url: null,
    captions_url: null,
    created_at: "2026-10-28T10:00:00Z",
    ready_at: null,
    ...over,
  };
}

describe("long file names (E2E 3)", () => {
  it("ClipRow puts the name in a shrinkable element with the full name as title", () => {
    render(
      <ul>
        <ClipRow
          clip={clip()}
          canAct
          canDeleteReady
          noSound={false}
          busy={false}
          onWatch={vi.fn()}
          onRetry={vi.fn()}
          onDelete={vi.fn()}
        />
      </ul>,
    );
    const name = screen.getByText(LONG);
    expect(name).toHaveClass("wm-clip-name");
    expect(name).toHaveAttribute("title", LONG);
    expect(name.parentElement).toHaveClass("wm-clip-line");
    expect(screen.getByText("Clip 1")).toBeInTheDocument();
  });

  it("ClipRow keeps the duration visible for a ready clip", () => {
    render(
      <ul>
        <ClipRow
          clip={clip({ status: "ready" })}
          canAct
          canDeleteReady
          noSound={false}
          busy={false}
          onWatch={vi.fn()}
          onRetry={vi.fn()}
          onDelete={vi.fn()}
        />
      </ul>,
    );
    expect(screen.getByText("0:12")).toHaveClass("wm-clip-time");
  });

  it("LocalRow shortens the name the same way", () => {
    render(
      <ul>
        <LocalRow
          item={{
            key: "k",
            file: new File(["x"], LONG),
            state: "waiting",
          } as never}
          ordinal={2}
          onRetry={vi.fn()}
          onRemove={vi.fn()}
          onCancel={vi.fn()}
        />
      </ul>,
    );
    const name = screen.getByText(LONG);
    expect(name).toHaveClass("wm-clip-name");
    expect(name).toHaveAttribute("title", LONG);
  });
});
