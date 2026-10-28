import type {
  ApiTransport,
  TransportRequest,
  TransportResponse,
  UploadRequest,
} from "./transport";

function parseBody(status: number, contentType: string, text: string): unknown {
  if (status === 204 || status === 304 || text === "") return undefined;
  if (!contentType.toLowerCase().includes("json")) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

function lowerHeaders(h: Headers): Record<string, string> {
  const out: Record<string, string> = {};
  h.forEach((v, k) => {
    out[k.toLowerCase()] = v;
  });
  return out;
}

function parseRawHeaders(raw: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of raw.split(/\r?\n/)) {
    const i = line.indexOf(":");
    if (i > 0) out[line.slice(0, i).trim().toLowerCase()] = line.slice(i + 1).trim();
  }
  return out;
}

/**
 * `fetch` transport (06 section 6.1). Same-origin cookies, JSON bodies,
 * multipart upload with progress through XMLHttpRequest (fetch has no upload
 * progress). Resolves for every HTTP status; rejects only on network failure.
 */
export class HttpTransport implements ApiTransport {
  async request(req: TransportRequest): Promise<TransportResponse> {
    const headers: Record<string, string> = { Accept: "application/json" };
    let body: string | undefined;
    if (req.body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(req.body);
    }
    Object.assign(headers, req.headers);
    const res = await fetch(req.path, {
      method: req.method,
      credentials: "same-origin",
      headers,
      body,
    });
    const text = res.status === 204 || res.status === 304 ? "" : await res.text();
    return {
      status: res.status,
      headers: lowerHeaders(res.headers),
      body: parseBody(res.status, res.headers.get("content-type") ?? "", text),
    };
  }

  upload(req: UploadRequest): Promise<TransportResponse> {
    return new Promise((resolve, reject) => {
      const { signal } = req;
      const aborted = () => new DOMException("Upload aborted", "AbortError");
      if (signal?.aborted) {
        reject(aborted());
        return;
      }
      const xhr = new XMLHttpRequest();
      xhr.open(req.method ?? "POST", req.path);
      xhr.withCredentials = true;
      xhr.setRequestHeader("Accept", "application/json");
      // Content-Type is left unset so the browser adds the multipart boundary.
      for (const [k, v] of Object.entries(req.headers ?? {})) {
        xhr.setRequestHeader(k, v);
      }
      const form = new FormData();
      form.append(req.field, req.file);
      for (const [k, v] of Object.entries(req.fields ?? {})) form.append(k, v);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) req.onProgress?.(e.loaded, e.total);
      };
      xhr.onerror = () => reject(new TypeError("Network error during upload"));
      xhr.onabort = () => reject(aborted());
      signal?.addEventListener("abort", () => xhr.abort(), { once: true });
      xhr.onload = () => {
        const headers = parseRawHeaders(xhr.getAllResponseHeaders());
        resolve({
          status: xhr.status,
          headers,
          body: parseBody(xhr.status, headers["content-type"] ?? "", xhr.responseText),
        });
      };
      xhr.send(form);
    });
  }
}
