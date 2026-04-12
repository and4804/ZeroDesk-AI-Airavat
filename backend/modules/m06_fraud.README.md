# M06 Fraud Signal Detection Engine

## Purpose
`m06_fraud.py` computes fraud risk for a loan session using multi-signal scoring and optional external verification checks.  
It exposes verification and scoring APIs under `/api/fraud`.

## Endpoints
### `POST /api/fraud/{session_id}/verify`
Runs standalone verification methods and stores a verification snapshot in session state.

Returns:
- `ip`
- `checked_at`
- `geolocation`
- `vpn_proxy`
- `device`

### `POST /api/fraud/{session_id}/score`
Runs verification first, then computes a weighted composite fraud score (`0-100`) from five signals.

Returns:
- `session_id`
- `composite_score`
- `risk_level` (`low`, `medium`, `high`)
- `signals`
- `verification`
- `weights`
- `timestamp`

### `GET /api/fraud/{session_id}`
Returns latest fraud report from session cache; falls back to persisted `fraud_scores` DB row.

## Fraud Signals and Weights
- `geo_mismatch`: `0.20`
- `device_anomaly`: `0.20`
- `age_inconsistency`: `0.15`
- `transcript_contradiction`: `0.25`
- `velocity_check`: `0.20`

## Verification Methods
### Geolocation verification
- Resolves client IP from session metadata.
- Calls geo API and normalizes response to city/region/country/lat/lon/ISP/proxy/hosting fields.
- For local or missing IP, returns non-verified local result.
- On API failure, falls back to session geolocation.

### VPN/Proxy verification
- Uses IPQualityScore when API key is configured.
- If unavailable or failing, derives signal from geolocation proxy flags.
- Produces `is_vpn`, `is_proxy`, optional `is_tor`, and `risk_score`.

### Device verification
- If external device API is configured, sends hashed fingerprint plus user-agent context.
- If unavailable or failing, uses deterministic local heuristics (headless, automation, emulator, short fingerprint, WebRTC disabled).
- Produces `risk_score`, `device_trust`, and flags.

## Provider Configuration
- `GEOIP_API_URL`
- `FRAUD_GEO_VERIFY_URL`
- `IPQUALITYSCORE_API_KEY`
- `IPQS_API_URL`
- `FRAUD_DEVICE_VERIFY_API_URL`
- `FRAUD_DEVICE_VERIFY_API_KEY`

## Current Actual Service Usage
- Geolocation currently uses `GEOIP_API_URL`, defaulting to `http://ip-api.com/json` (ip-api style contract), unless `FRAUD_GEO_VERIFY_URL` is set.
- VPN/proxy external verification uses IPQualityScore only when `IPQUALITYSCORE_API_KEY` is set.
- Device external verification runs only when `FRAUD_DEVICE_VERIFY_API_URL` is set.
- When external providers are not configured or fail, M06 falls back to local/session-based heuristics and still returns a complete verification payload.

## Risk Classification
- `low`: composite score `<= FRAUD_MEDIUM_THRESHOLD`
- `medium`: composite score `> FRAUD_MEDIUM_THRESHOLD` and `<= FRAUD_HIGH_THRESHOLD`
- `high`: composite score `> FRAUD_HIGH_THRESHOLD`

## Swagger Test Flow
1. `POST /api/sessions/create` and copy `session_id`.
2. `POST /api/sessions/{session_id}/metadata` with device fingerprint and user-agent.
3. `POST /api/fraud/{session_id}/verify` and confirm `geolocation`, `vpn_proxy`, `device`.
4. `POST /api/fraud/{session_id}/score` and confirm `composite_score`, `risk_level`, `signals`, `verification`.
5. `GET /api/fraud/{session_id}` and confirm report retrieval.

## Known Limitations
- Localhost sessions do not produce real external geo/vpn intelligence.
- External verification APIs use bounded timeout and fail-safe fallbacks.
- DB persistence stores signal breakdown and risk level; full verification snapshot is primarily session-state output.
