# Mobile Pairing API Design

**Date:** 2026-01-10
**Status:** Draft
**Author:** Engineering Team

## Overview

Mobile pairing API for Volant iOS app to connect to Amelia server instances via QR code scanning. This document describes the server-side API changes required to support secure device pairing, token management, and ongoing authentication for mobile clients.

## Pairing Flow

The complete pairing flow consists of the following steps:

1. User requests pairing QR (Dashboard button or `amelia pair` CLI command)
2. Server generates one-time token (expires in 60 seconds)
3. Display QR containing: `amelia://<ip>:<port>?pair=<one-time-token>`
4. iOS app scans QR
5. App calls POST /api/pair/exchange with the one-time token
6. Server validates token, generates persistent device token
7. Server returns device_token, device_id, server_name
8. App stores credentials in Keychain
9. All future requests include Authorization: Bearer <device_token>

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Dashboard  │     │   Server    │     │  iOS App    │
│   or CLI    │     │             │     │             │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │  POST /api/pair/  │                   │
       │     generate      │                   │
       │──────────────────>│                   │
       │                   │                   │
       │  {pair_token,     │                   │
       │   qr_url}         │                   │
       │<──────────────────│                   │
       │                   │                   │
       │   Display QR      │                   │
       │   ════════════    │                   │
       │                   │                   │
       │                   │   Scan QR code    │
       │                   │<──────────────────│
       │                   │                   │
       │                   │  POST /api/pair/  │
       │                   │     exchange      │
       │                   │<──────────────────│
       │                   │                   │
       │                   │  {device_token,   │
       │                   │   device_id}      │
       │                   │──────────────────>│
       │                   │                   │
       │                   │  Store in         │
       │                   │  Keychain         │
       │                   │                   │
```

## New API Endpoints

### POST /api/pair/generate

Generates a one-time pairing token and QR URL.

**Authentication:** Existing session (dashboard) or local-only access (CLI)

**Request:** None (empty body)

**Response:**

```json
{
  "pair_token": "otp_xxxxxxxxxxxx",
  "qr_url": "amelia://192.168.1.100:8420?pair=otp_xxxxxxxxxxxx",
  "expires_at": "2026-01-10T12:01:00Z"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `pair_token` | string | One-time pairing token (prefixed with `otp_`) |
| `qr_url` | string | Complete URL for QR code generation |
| `expires_at` | string | ISO 8601 timestamp when token expires (60 seconds from generation) |

**Errors:**

| Status | Description |
|--------|-------------|
| 429 | Rate limit exceeded (max 5 tokens per minute) |

---

### POST /api/pair/exchange

Exchanges one-time pairing token for persistent device token.

**Authentication:** None (the pair_token serves as authentication)

**Request:**

```json
{
  "pair_token": "otp_xxxxxxxxxxxx",
  "device_name": "iPad Pro",
  "device_model": "iPad Pro 12.9-inch"
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pair_token` | string | Yes | One-time token from QR code |
| `device_name` | string | Yes | User-facing device name |
| `device_model` | string | No | Device model identifier |

**Response:**

```json
{
  "device_token": "dev_xxxxxxxxxxxx",
  "device_id": "uuid",
  "server_name": "My Mac Studio"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `device_token` | string | Persistent bearer token (prefixed with `dev_`) |
| `device_id` | string | UUID identifying this paired device |
| `server_name` | string | Human-readable name of the Amelia server |

**Errors:**

| Status | Description |
|--------|-------------|
| 400 | Invalid or expired pair token |
| 410 | Token already used |

---

### GET /api/pair/devices

List all paired devices.

**Authentication:** Session (dashboard) or local-only access

**Request:** None

**Response:**

```json
{
  "devices": [
    {
      "device_id": "uuid",
      "device_name": "iPad Pro",
      "device_model": "iPad Pro 12.9-inch",
      "paired_at": "2026-01-10T12:00:00Z",
      "last_seen": "2026-01-10T14:30:00Z"
    }
  ]
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `devices` | array | List of paired devices |
| `devices[].device_id` | string | UUID of the device |
| `devices[].device_name` | string | User-facing device name |
| `devices[].device_model` | string | Device model identifier |
| `devices[].paired_at` | string | ISO 8601 timestamp of pairing |
| `devices[].last_seen` | string | ISO 8601 timestamp of last activity |

---

### DELETE /api/pair/devices/{device_id}

Revoke a paired device. Immediately invalidates its device token.

**Authentication:** Session (dashboard) or local-only access

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `device_id` | string | UUID of device to revoke |

**Response:** 204 No Content

**Errors:**

| Status | Description |
|--------|-------------|
| 404 | Device not found |

## CLI Addition

### `amelia pair` Command

New CLI command for initiating mobile pairing:

```bash
amelia pair [options]

Options:
  --timeout <seconds>   Override default 60-second expiration
  --json                Output token data as JSON instead of QR
```

**Behavior:**

1. Calls POST /api/pair/generate
2. Prints QR code to terminal using Unicode block characters
3. Shows expiration countdown below QR code
4. Auto-regenerates QR when expired (or on keypress)
5. Exits on Ctrl+C or successful pairing

**Example Output:**

```
Scan this QR code with the Volant iOS app:

█████████████████████████████
█████████████████████████████
████ ▄▄▄▄▄ █▀▄█▀█ ▄▄▄▄▄ ████
████ █   █ █▄▀▄ █ █   █ ████
████ █▄▄▄█ █ ▄▀██ █▄▄▄█ ████
████▄▄▄▄▄▄▄█▄▀▄█▄█▄▄▄▄▄▄▄████
█████████████████████████████
█████████████████████████████

Token expires in: 45s
Press [R] to regenerate, [Q] to quit
```

## Dashboard Addition

### "Connect Mobile" Button

Located in the dashboard header or settings panel.

**Modal Contents:**

1. **QR Code Display**
   - Large, scannable QR code
   - Visual countdown timer
   - Auto-refresh when expired

2. **Paired Devices List**
   - Device name and model
   - Paired date and last seen
   - "Revoke" button for each device

**Mock UI:**

```
┌─────────────────────────────────────────────┐
│  Connect Mobile Device                    ✕ │
├─────────────────────────────────────────────┤
│                                             │
│         ┌─────────────────┐                 │
│         │                 │                 │
│         │    [QR CODE]    │                 │
│         │                 │                 │
│         └─────────────────┘                 │
│                                             │
│         Expires in: 45 seconds              │
│         [Regenerate QR]                     │
│                                             │
├─────────────────────────────────────────────┤
│  Paired Devices                             │
│                                             │
│  📱 iPad Pro                                │
│     iPad Pro 12.9-inch                      │
│     Paired: Jan 10, 2026 • Last seen: 2h    │
│     [Revoke]                                │
│                                             │
│  📱 iPhone 15 Pro                           │
│     iPhone 15 Pro Max                       │
│     Paired: Jan 8, 2026 • Last seen: 5m     │
│     [Revoke]                                │
│                                             │
└─────────────────────────────────────────────┘
```

## Database Schema

### New Table: `paired_devices`

Stores information about paired mobile devices.

```sql
CREATE TABLE paired_devices (
    id TEXT PRIMARY KEY,                          -- UUID
    device_token_hash TEXT NOT NULL,              -- bcrypt hash of token
    device_name TEXT,                             -- User-facing name
    device_model TEXT,                            -- Model identifier
    paired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP,
    revoked_at TIMESTAMP                          -- NULL if active
);

CREATE INDEX idx_paired_devices_token_hash ON paired_devices(device_token_hash);
CREATE INDEX idx_paired_devices_last_seen ON paired_devices(last_seen);
```

### New Table: `pairing_tokens`

Stores one-time pairing tokens with short expiration.

```sql
CREATE TABLE pairing_tokens (
    token_hash TEXT PRIMARY KEY,    -- SHA-256 hash of one-time token
    expires_at TIMESTAMP NOT NULL,  -- 60 seconds from creation
    used_at TIMESTAMP,              -- NULL if unused
    used_by_device_id TEXT          -- References paired_devices.id
);

CREATE INDEX idx_pairing_tokens_expires ON pairing_tokens(expires_at);
```

### Token Cleanup

Expired and used tokens should be cleaned up periodically:

```sql
-- Run every hour or on server startup
DELETE FROM pairing_tokens
WHERE expires_at < datetime('now', '-1 hour')
   OR used_at < datetime('now', '-1 day');
```

## Security Considerations

### Token Security

| Aspect | Implementation |
|--------|----------------|
| One-time token expiration | 60 seconds |
| One-time token usage | Single use only |
| Device token storage | bcrypt hash (cost factor 10) |
| Token revocation | Immediate effect |

### Network Security

- All pairing endpoints are local-network only (no cloud exposure in v1)
- Server binds to local network interface only
- mDNS/Bonjour discovery limited to local network

### Rate Limiting

| Endpoint | Limit |
|----------|-------|
| POST /api/pair/generate | 5 requests per minute |
| POST /api/pair/exchange | 10 requests per minute |

### Token Generation

```python
# One-time pairing token (22 chars, URL-safe)
pair_token = "otp_" + secrets.token_urlsafe(16)

# Device token (32 chars, URL-safe)
device_token = "dev_" + secrets.token_urlsafe(24)
```

## Authentication Middleware Update

Update existing auth middleware to accept device tokens in addition to session authentication.

### Middleware Logic

```python
def authenticate(request):
    # Check for Bearer token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]

        if token.startswith("dev_"):
            # Device token authentication
            token_hash = bcrypt_hash(token)
            device = db.query(
                "SELECT * FROM paired_devices WHERE device_token_hash = ? AND revoked_at IS NULL",
                token_hash
            )

            if device:
                # Update last_seen
                db.execute(
                    "UPDATE paired_devices SET last_seen = CURRENT_TIMESTAMP WHERE id = ?",
                    device.id
                )
                request.device = device
                return True

    # Fall back to existing session auth
    return existing_session_auth(request)
```

### Request Context

When authenticated via device token, the request context includes:

```python
request.device = {
    "device_id": "uuid",
    "device_name": "iPad Pro",
    "device_model": "iPad Pro 12.9-inch"
}
```

## Implementation Checklist

- [ ] Database migrations for new tables
- [ ] POST /api/pair/generate endpoint
- [ ] POST /api/pair/exchange endpoint
- [ ] GET /api/pair/devices endpoint
- [ ] DELETE /api/pair/devices/{device_id} endpoint
- [ ] `amelia pair` CLI command
- [ ] QR code generation (terminal and web)
- [ ] Dashboard modal component
- [ ] Auth middleware update
- [ ] Rate limiting middleware
- [ ] Token cleanup job
- [ ] Integration tests
- [ ] iOS SDK documentation

## Future Considerations

- **Push notifications:** Device registration could include push token
- **Cloud relay:** Optional cloud proxy for remote access
- **Multi-user:** Associate devices with specific user accounts
- **Device limits:** Maximum number of paired devices per server
