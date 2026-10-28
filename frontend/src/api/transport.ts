export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface TransportRequest {
  method: HttpMethod;
  /** Path including the `/api` prefix and any query string. */
  path: string;
  /** JSON body; serialised by the transport. */
  body?: unknown;
  headers?: Record<string, string>;
}

export interface TransportResponse {
  status: number;
  /** Header names are lower-case. */
  headers: Record<string, string>;
  /** Parsed JSON body; undefined for 204 and 304. */
  body: unknown;
}

export interface UploadRequest {
  method?: "POST" | "PUT";
  path: string;
  /** Multipart field name: `file` for clips, `photo` for dog photos. */
  field: string;
  file: File;
  /** Extra text fields, for example `client_request_id`. */
  fields?: Record<string, string>;
  headers?: Record<string, string>;
  onProgress?: (loaded: number, total: number) => void;
}

/**
 * Wire-level port. HttpTransport (fetch) and MockTransport implement it.
 * Implementations resolve for every HTTP status; ApiClient turns error
 * envelopes into ApiError. They reject only on network failure.
 */
export interface ApiTransport {
  request(req: TransportRequest): Promise<TransportResponse>;
  upload(req: UploadRequest): Promise<TransportResponse>;
}
