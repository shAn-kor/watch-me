# ADR-0027: One container, two processes, one volume; Oracle Cloud Always Free A1, fallback GCP e2-micro + Cloudflare R2

- Status: Accepted (host capacity unverified)
- Date: 2026-10-28

## Context

- Hackathon with a US$150 credit; nonprofit, low-cost goal (ADR-0010).
- Checked 2026-10-28 from official pricing pages (DESIGN section 14): Oracle Always Free A1 up to 2 OCPU, 12 GB RAM, 200 GB block, 10 TB/month outbound, home region only. GCP e2-micro: 1 VM in us-west1/us-central1/us-east1, 30 GB disk, 1 GB/month outbound (too small for video). Cloudflare R2: 10 GB free, free egress.
- Rejected platforms: Render free (no persistent disk, sleeps), Railway (0.5 GB volume), Fly.io (no free tier), Hugging Face Docker Spaces (needs PRO), Koyeb (no free web service found).

## Decision

- One container image with two processes (api, worker) and one volume (SQLite + files). Compose file in the repo.
- Host: Oracle Cloud Always Free A1 VM. Fallback: GCP e2-micro with clips served from Cloudflare R2.

## Alternatives considered

- Render, Railway, Fly.io, Hugging Face Spaces, Koyeb: rejected for the reasons above.
- GCP e2-micro alone: rejected, outbound too small for video.

## Consequences

- Positive: free, a full VM with Docker and ffmpeg, no sleep.
- Negative: needs a non-prepaid credit/debit card; idle A1 VMs (CPU, network, memory all under 20% for 7 days) may be reclaimed; A1 capacity at signup is unverified.
- Follow-up: confirm card and capacity; if blocked, switch to the fallback with an R2 `Storage` adapter (ADR-0018).

## Related

DESIGN sections 13, 14; ADR-0016, ADR-0017, ADR-0018.
