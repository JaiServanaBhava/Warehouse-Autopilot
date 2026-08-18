# Security Policy — Warehouse Autopilot

## 1. Supported Versions
Warehouse Autopilot adheres to industry security standards for autonomous supply chain and logistics operations.

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## 2. Security Architecture & Threat Mitigation

### A. Environment Variable & Secret Isolation
* **Zero Hardcoded Credentials**: All API secrets (Google Gemini API Key, Twilio Account SID, Auth Token, SMTP Passwords) are strictly loaded dynamically via environment variables (`.env`).
* **Version Control Protection**: `.gitignore` strictly bans `.env`, `.env.local`, SQLite databases (`*.db`, `*.sqlite`), and cached credentials from being tracked in git.
* **Safe Template**: `.env.example` provides sanitised placeholders with clear format specifications without revealing production tokens.

### B. Network & Transport Security
* **OWASP Security Headers Middleware**:
  * `X-Content-Type-Options: nosniff` (prevents MIME type sniffing)
  * `X-Frame-Options: DENY` (clickjacking defense)
  * `X-XSS-Protection: 1; mode=block` (cross-site scripting mitigation)
  * `Referrer-Policy: strict-origin-when-cross-origin` (prevents path leakage)
  * `Permissions-Policy: camera=(), microphone=(), geolocation=()` (restricts browser hardware access)
  * `Content-Security-Policy`: Restricts scripts, styles, and data sources strictly to legitimate endpoints.
* **Strict CORS Enforcement**: Explicit origin validation configurable via `CORS_ORIGINS`.

### C. Injection & Data Integrity
* **Parameterized SQLite Queries**: All database queries utilize parameterized SQL statements to eliminate SQL Injection (SQLi) vulnerabilities.
* **Input Validation & Sanitization**: Strict Pydantic models validate incoming payloads for type correctness, bounds, and string length before reaching internal business logic.
* **Error Masking**: Production errors never leak raw stack traces or internal server paths to API consumers.

## 3. Reporting a Vulnerability
If you discover a security vulnerability in Warehouse Autopilot, please report it responsibly by contacting the maintainer or opening a private security advisory on GitHub.
