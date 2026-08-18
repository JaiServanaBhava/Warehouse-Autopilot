<div align="center">

<img src="https://capsule-render.vercel.app/api?type=rect&height=150&text=WAREHOUSE%20AUTOPILOT&fontSize=40&fontColor=ffffff&fontAlignY=48&desc=AI%20Operations%20%7C%20Real-Time%20Fulfillment%20%7C%20Automated%20Response&descAlignY=72&descSize=14&color=0:111827,50:1D4ED8,100:0F766E" width="100%" alt="Warehouse Autopilot banner"/>

**Autonomous AI Operations & Supply Chain Command Center**

[![Live Demo](https://img.shields.io/badge/🚀_Live_Demo-Open_Command_Center-2F80ED?style=for-the-badge)](https://warehouse-autopilot.onrender.com)
[![Deploy on Render](https://img.shields.io/badge/Deploy-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://render.com/deploy)

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white)
![Gemini](https://img.shields.io/badge/AI-Gemini_2.5_Flash-4285F4?style=flat-square&logo=google&logoColor=white)
![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-111827?style=flat-square)

</div>

---

## 📸 Screenshot

> Add your main command-center screenshot here before submitting (save it into a `/screenshots` folder in the repo, keep it under ~300KB so the repo stays under the 10MB limit).

![Warehouse Autopilot Command Center](./screenshots/command-center.png)

Give it real `alt` text describing what it shows (not just a filename) — this also feeds directly into your Accessibility score.

---

## 🎨 Visual & Motion Design

The command center uses a modern operations-control-room aesthetic:

- ✨ Animated hero entrance and subtle gradient motion in the header
- 💫 Glassmorphism cards with soft depth
- 📈 Animated KPI counters and progress indicators
- 🔴 Pulsing critical-status indicators, 🟢 live connection heartbeat
- 🔄 Skeleton/loading transitions, smooth section transitions
- 🔔 Toast notifications for real-time events
- 💡 AI response typing/streaming effect in the Copilot
- 📱 Responsive micro-interactions on mobile

> Motion is used to communicate state (critical events get stronger emphasis), not to distract from the underlying data — and every animated/color cue is paired with text or an icon so it isn't the only signal (see Accessibility section).

---

## 🎯 Overview

**Warehouse Autopilot** is an AI-assisted warehouse operations platform. Instead of only displaying inventory problems, it detects operational risk, ranks recommended actions, explains its reasoning, and can trigger the resulting notification/procurement workflow.

**Loop:** Live warehouse data → Decision Engine (detect, rank, score) → Recommended actions → Execute (inventory/orders) or Notify (email / WhatsApp / supplier PO).

---

## 🏆 Why It's Different

Most warehouse dashboards stop at *visibility* — they show you a problem and leave the response to a human. Warehouse Autopilot closes the loop.

| Typical WMS Dashboard | Warehouse Autopilot |
|---|---|
| Displays historical/current problems | 🧠 Detects and **prioritizes** operational risk |
| Manual analysis | ⚡ Ranked, one-click action queue |
| Manual alerting | 📧 Automatic notification workflows |
| Manual supplier reorder process | 📦 Auto-generated supplier purchase orders |
| Generic chatbot | 🤖 Warehouse-aware Gemini Copilot with live context |
| Separate tools per function | 🗂️ One unified command center |

The design principle: don't just tell the team *what's wrong* — tell them *what to do next*, and help them do it.

---

## ✨ Key Features

| Capability | What it does |
|---|---|
| 🧠 Decision Engine | Turns warehouse signals into a prioritized, ranked action queue |
| 📦 Inventory Intelligence | Detects shortages, runway risk, and allocation issues |
| 🎯 Order Risk Scoring | Flags orders likely to miss fulfillment targets |
| ⚡ Action Queue | Converts recommendations into one-click executable operations |
| 🤖 Warehouse Copilot | Gemini 2.5 Flash assistant grounded in live warehouse context |
| 📧 Critical Alerts | Automated email/WhatsApp fan-out on critical events |
| 💬 WhatsApp Workflow | Brings urgent alerts straight to floor-level staff |
| 📦 Supplier PO Workflow | Generates replenishment purchase orders from detected shortages |
| 📱 QR Passport | Per-product QR code exposing live stock state to floor staff |
| 🗺️ Fulfillment Pipeline | Tracks picking → packing → QC → dispatch |
| 📊 Notification Outbox | Delivery status/timestamp log for every automated message, for auditability |
| ⚙️ In-app Settings | Configure integrations without editing source code |

---

## 🔍 Feature Deep Dive

### 1. 🧠 Autonomous Decision & Action Engine
Evaluates inventory runway, stock availability, order deadlines, customer priority, zone bottlenecks, and worker capacity to produce a ranked, executable action queue. Each recommendation includes the exact action, estimated impact, a confidence score, the reasoning behind it, and one-click execution.

### 2. 📧 Automated Critical-Event Notification Fan-Out
When a critical event occurs — stockout, SLA risk, QC failure — the platform can fan out to business email, WhatsApp, and a supplier purchase order automatically, without someone manually composing each alert. The Notification Outbox logs delivery status, timestamps, and recipients for traceability.

### 3. 🤖 Gemini 2.5 Flash Warehouse Copilot
A dedicated AI workspace grounded in live warehouse context — current stockouts, at-risk orders, operational health, zone congestion, worker assignments — with quick actions like "What should I do now?", "Critical shortages," "Draft reorder PO." Conversation history persists locally across refreshes.

### 4. 📱 QR Intelligence Passport
Each product gets a scannable QR passport exposing live stock quantity, reserved/damaged/usable units, estimated days to stockout, reorder recommendation, location, supplier, and price. If inventory changes after a label is printed, the system flags it **QR OUTDATED** and offers regeneration — so floor staff never act on a stale label.

### 5. 🗺️ Live Fulfillment Pipeline
Tracks the order lifecycle end to end: picking (bin route, SKU allocation, assigned picker) → packing (carton recommendation, weight, scan status) → QC (checklist, pass/fail, exception creation) → dispatch (carrier, AWB tracking, dock bay).

### 6. ⚙️ In-App Credential & Alert Configuration
Alert email, supplier PO recipient, WhatsApp recipient, and Twilio credentials are all configurable from Settings — no backend edits needed, which makes the demo easy for evaluators to test live.

---

## Architecture

```
Presentation   HTML / CSS / Vanilla JS, responsive UI
Real-time      Server-Sent Events for live operational updates
Application    FastAPI — decision engine, fulfillment logic
Intelligence   Gemini 2.5 Flash — context-aware copilot
Communication  Email / WhatsApp / Supplier PO workflows (Twilio)
Data           SQLite (WAL mode) — inventory, orders, settings
```

### Technology Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Python 3.11 |
| AI | Google Gemini 2.5 Flash |
| Database | SQLite (WAL mode) |
| Frontend | HTML + CSS + Vanilla JavaScript |
| Real-time updates | Server-Sent Events (SSE) |
| Communications | Twilio (Email + WhatsApp) |
| Deployment | Render |

---

## Security

> Fill this section in with what is *actually true* of your implementation before submitting — an inaccurate security section will cost you more than an honest, shorter one.

Implemented / in place:
- [ ] Secrets loaded from environment variables only; no credentials committed to the repo
- [ ] `.env` (and any file with real keys) is in `.gitignore`
- [ ] All database queries are parameterized (no string-built SQL)
- [ ] Input validation on every API endpoint that accepts user data (Pydantic models / explicit checks)
- [ ] Authentication/authorization on state-changing endpoints (applying an action, changing settings, triggering a notification)
- [ ] Rate limiting or basic abuse protection on public endpoints
- [ ] Webhook/event payloads are validated before processing
- [ ] HTTPS enforced in the deployed environment
- [ ] Logs never contain secrets, tokens, or full customer PII
- [ ] Dependency versions pinned in `requirements.txt`

Known limitations (be explicit — reviewers penalize silence more than an honest scope note):
- e.g. "No per-user auth yet — single shared operator session, acceptable for hackathon scope but flagged for production."

---

## Accessibility

> Same rule as above — only claim what you tested.

Implemented / in place:
- [ ] Semantic HTML (`<nav>`, `<main>`, `<button>`, headings in order — not `<div>` soup)
- [ ] All interactive elements reachable and operable via keyboard alone (tab order, focus states visible)
- [ ] `alt` text on all meaningful images/icons; decorative icons marked `aria-hidden`
- [ ] ARIA labels on icon-only buttons and dynamic regions (e.g. live alert feed uses `aria-live`)
- [ ] Color is never the only signal for status (priority badges pair color with text/icon, for color-blind users)
- [ ] Text contrast meets WCAG AA (4.5:1 for body text) — check the glassmorphism cards specifically, low-contrast text on translucent backgrounds is a common failure
- [ ] Forms have associated `<label>` elements, not placeholder-only labeling
- [ ] Responsive layout tested at 200% browser zoom

If any of these are unchecked, they're almost certainly why Accessibility scored 30 — this is the fastest lever you have to raise your total score, since it's usually a few hours of front-end fixes rather than new features.

---

## Testing

The project includes scripts for validating major workflows:

```bash
python backend/test_startup_demo_dispatch.py   # notification workflow
python backend/test_twilio_email_dispatch.py   # email dispatch
python backend/test_qr_flow.py                 # QR generation/validation
python backend/test_reset_and_po.py            # settings persistence / PO workflow
```

External communication tests require valid Twilio/Gemini credentials configured in the environment.

> If you have unit tests beyond these integration scripts, list them here with how to run them and what they cover — reviewers scoring "Testing" are looking for evidence of validation, not just that the app runs.

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/your-username/warehouse-autopilot.git
cd warehouse-autopilot
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file (never commit this):

```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash

TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_EMAIL_FROM=your_email_sender
TWILIO_WHATSAPP_FROM=whatsapp:+1xxxxxxxxxx
TWILIO_WHATSAPP_TO=whatsapp:+91xxxxxxxxxx
TWILIO_CONTENT_SID=HXxxxxxxxxxxxx

COMPANY_EMAIL=your_company_email
SUPPLIER_PO_RECIPIENT=supplier_email

AUTOMATIC_EMAIL_ENABLED=true
AUTOMATIC_WHATSAPP_ENABLED=true
```

### 3. Run

```bash
uvicorn backend.server:app --reload --port 8000
```

Open `http://localhost:8000`.

### Deploy on Render

```
Build Command:  pip install -r requirements.txt
Start Command:  uvicorn backend.server:app --host 0.0.0.0 --port $PORT
```

Add the environment variables above in the Render dashboard.

---

## Judge Demo Flow (90 seconds)

1. Open the command center, show live warehouse health
2. Trigger/identify a critical shortage
3. Decision Engine ranks the risk
4. Copilot explains what's happening and why
5. Operator applies the recommended action
6. Automated alert workflow fires (email/WhatsApp)
7. Supplier PO is generated
8. Notification Outbox shows delivery status
9. QR Passport confirms current product state

---

## Assumptions

- Single shared operator role; no per-user accounts (see Security section)
- SQLite is sufficient for the hackathon's data volume; not sized for production multi-warehouse load
- Twilio and Gemini API keys are provisioned by the evaluator/judge or supplied via demo credentials
- Live demo availability depends on the Render free-tier service being awake

---

## 🌐 Live Demo

<p align="center">
  <a href="https://warehouse-autopilot.onrender.com">
    <img src="https://img.shields.io/badge/🚀_OPEN_LIVE_DEMO-2F80ED?style=for-the-badge" alt="Open Live Demo"/>
  </a>
</p>

> Demo availability depends on the deployed service being online and correctly configured (free-tier Render services can take ~30s to wake up).

---

## Project Status

Hackathon submission demonstrating autonomous decision support, AI-assisted operations analysis, real-time visibility, and automated critical-event communication for warehouse fulfillment.

**Predict → Decide → Execute → Notify**
