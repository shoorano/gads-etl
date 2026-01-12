# Storage Realism Specification

## 1. Object storage target model
- **API**: S3-compatible operations (PUT/GET/HEAD/DELETE) with virtual-host or path-style addressing.  
- **Production target**: Hetzner Object Storage configured with S3 API credentials.  
- **Local parity target**: MinIO running in Docker or on localhost, exposing the same S3 semantics.  
- The sink interface must remain vendor-neutral so any S3-compatible provider can be swapped in via configuration.

## 2. ObjectStorageRawSink semantics
- Implements the existing `RawSink` interface:  
  - `write_partition(partition_key, run_id) -> PartitionWriter`  
  - `open_partition(partition_key, run_id) -> PartitionReader`  
  - `list_partitions(partition_key) -> list[str]` (run_ids)
- `PartitionWriter` streams payload rows directly into the target bucket (using multipart uploads for large files).  
- `finalize(metadata)` uploads metadata.json last, acting as the sealing step.  
- `PartitionReader` downloads payload.jsonl & metadata.json from the bucket.  
- `list_partitions` enumerates `run_id=` prefixes under the logical partition path.

## 3. Object layout mapping
Use the canonical filesystem layout as object key prefixes:
```
<root>/<source>/
  customer_id=<id>/
    query_name=<name>/
      logical_date=YYYY-MM-DD/
        run_id=<iso_ts>/
          payload.jsonl
          metadata.json
```
Examples (bucket `gads`, root `raw`):
- `raw/google_ads/customer_id=123/query_name=campaign/logical_date=2024-06-01/run_id=2024-06-02T00:00:00.000Z/payload.jsonl`
- `.../metadata.json`
Folders are represented via prefix conventions; no additional markers are needed.

## 4. Finalization / partial visibility rules
- Payload upload first (stream or multipart). Metadata upload second as the “seal”.  
- While payload exists without metadata, the partition is considered incomplete; validators/consumers must check for metadata presence.  
- Idempotency: if an upload fails mid-stream, the partial object is discarded (abort multipart) and a new writer may restart with the same run_id.  
- To avoid overwriting existing partitions, writers must check `metadata.json` presence before writing; if it exists, finalize must refuse to overwrite.  
- Readers treat metadata existence as the signal that the partition is finalized; no state change occurs until validator marks success.

## 5. Configuration contract
- Backend selection via config/env only (no code changes):  
  - `RAW_SINK=filesystem` (default)  
  - `RAW_SINK=object`  
- Required env/config for object sink:  
  - `RAW_SINK_ENDPOINT_URL` (MinIO/Hetzner)  
  - `RAW_SINK_REGION` (optional; default set per provider)  
  - `RAW_SINK_BUCKET`  
  - `RAW_SINK_PREFIX` (root path, e.g., `raw`)  
  - `RAW_SINK_ACCESS_KEY_ID` / `RAW_SINK_SECRET_ACCESS_KEY` (env-only, never committed)  
- Secrets must be injected via env/secret manager. No hardcoded credentials.

## 6. Local/CI/Prod matrix
- **Local dev**: filesystem sink (fast, no network).  
- **CI fast**: filesystem sink (default job).  
- **CI parity**: optional job runs against MinIO to verify object sink behavior.  
- **Prod**: Hetzner Object Storage via S3-compatible endpoint.  
Switching is controlled through configuration/env variables only.

## 7. Testing strategy
- **Unit tests**: Source-only tests covering key mapping, metadata-last ordering, overwrite refusal. No network calls.  
- **Integration tests** (marked `minio` or `parity`):  
  - Spin up MinIO container.  
  - Verify writer finalize creates both objects.  
  - Verify reader loads payload + metadata.  
  - Verify list_partitions returns run_ids.  
  - Verify attempts to rewrite an existing finalized run fail.  
- Tests requiring MinIO are opt-in (CI parity job).

## 8. Deployment notes
- Ansible (or equivalent) must provision:  
  - Environment variables for sink selection & credentials.  
  - Access keys injected via secret management (Vault, SOPS).  
  - Optional MinIO service for parity environments.  
- No scheduler/daemon definitions here; only mention the need to supply env vars and network access.

## 9. Invariants
- Finalized partitions are never overwritten (metadata-last sealing).  
- Metadata upload always happens after payload upload.  
- State authority is unchanged; consumers still rely exclusively on PartitionState.  
- Consumers remain unaffected regardless of sink implementation.

## 10. Explicit non-goals
- No warehouse loading or downstream modeling.  
- No performance tuning or cost optimization.  
- No observability/logging changes.  
- No orchestration or scheduler modifications.
