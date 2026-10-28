import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpTransport } from "./httpTransport";

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubFetch(res: Response) {
  const f = vi.fn().mockResolvedValue(res);
  vi.stubGlobal("fetch", f);
  return f;
}

describe("HttpTransport.request", () => {
  it("sends JSON with same-origin credentials and lower-cases headers", async () => {
    const f = stubFetch(
      new Response(JSON.stringify({ ok: 1 }), {
        status: 200,
        headers: { "Content-Type": "application/json", ETag: 'W/"x"' },
      }),
    );
    const r = await new HttpTransport().request({
      method: "POST",
      path: "/api/x",
      body: { a: 1 },
      headers: { "X-CSRF-Token": "t" },
    });
    const [url, init] = f.mock.calls[0]!;
    expect(url).toBe("/api/x");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(init.body).toBe('{"a":1}');
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(init.headers["X-CSRF-Token"]).toBe("t");
    expect(r.status).toBe(200);
    expect(r.headers.etag).toBe('W/"x"');
    expect(r.body).toEqual({ ok: 1 });
  });

  it("resolves for error statuses and returns undefined for 204/304", async () => {
    stubFetch(new Response(null, { status: 204 }));
    const r = await new HttpTransport().request({ method: "DELETE", path: "/api/x" });
    expect(r).toMatchObject({ status: 204, body: undefined });
    stubFetch(
      new Response(JSON.stringify({ error: { code: "not_found" } }), {
        status: 404,
        headers: { "content-type": "application/json" },
      }),
    );
    const e = await new HttpTransport().request({ method: "GET", path: "/api/y" });
    expect(e.status).toBe(404);
    expect(e.body).toEqual({ error: { code: "not_found" } });
  });

  it("rejects on network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("down")));
    await expect(
      new HttpTransport().request({ method: "GET", path: "/api/z" }),
    ).rejects.toThrow();
  });

  it("tolerates a non-JSON error body", async () => {
    stubFetch(new Response("<html>bad gateway</html>", { status: 502 }));
    const r = await new HttpTransport().request({ method: "GET", path: "/api/z" });
    expect(r.status).toBe(502);
    expect(r.body).toBeUndefined();
  });
});

class FakeXhr {
  static last: FakeXhr;
  upload: { onprogress: ((e: ProgressEvent) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  status = 201;
  responseText = JSON.stringify({ clip: { id: "c1" } });
  method = "";
  url = "";
  headers: Record<string, string> = {};
  sent: FormData | null = null;
  withCredentials = false;
  constructor() {
    FakeXhr.last = this;
  }
  open(m: string, u: string) {
    this.method = m;
    this.url = u;
  }
  setRequestHeader(k: string, v: string) {
    this.headers[k] = v;
  }
  getAllResponseHeaders() {
    return "Content-Type: application/json\r\nETag: abc\r\n";
  }
  send(body: FormData) {
    this.sent = body;
    this.upload.onprogress?.({ lengthComputable: true, loaded: 5, total: 10 } as ProgressEvent);
    queueMicrotask(() => this.onload?.());
  }
}

describe("HttpTransport.upload", () => {
  it("posts multipart with progress and extra fields", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const onProgress = vi.fn();
    const file = new File(["abc"], "a.mp4", { type: "video/mp4" });
    const r = await new HttpTransport().upload({
      path: "/api/sessions/s1/clips",
      field: "file",
      file,
      fields: { client_request_id: "r1" },
      headers: { "X-CSRF-Token": "t" },
      onProgress,
    });
    const x = FakeXhr.last;
    expect(x.method).toBe("POST");
    expect(x.url).toBe("/api/sessions/s1/clips");
    expect(x.headers["X-CSRF-Token"]).toBe("t");
    expect(x.headers["Content-Type"]).toBeUndefined();
    expect((x.sent!.get("file") as File).name).toBe("a.mp4");
    expect(x.sent!.get("client_request_id")).toBe("r1");
    expect(onProgress).toHaveBeenCalledWith(5, 10);
    expect(r.status).toBe(201);
    expect(r.body).toEqual({ clip: { id: "c1" } });
    expect(r.headers.etag).toBe("abc");
  });

  it("rejects on a network error", async () => {
    class Boom extends FakeXhr {
      send() {
        queueMicrotask(() => this.onerror?.());
      }
    }
    vi.stubGlobal("XMLHttpRequest", Boom);
    await expect(
      new HttpTransport().upload({
        path: "/p",
        field: "file",
        file: new File(["x"], "a.mp4"),
      }),
    ).rejects.toThrow();
  });
});
