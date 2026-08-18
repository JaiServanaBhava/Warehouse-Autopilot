```
### 3. Start the Application
```bash
python -m uvicorn backend.server:app --reload --port 8000
```
Open [http://localhost:8000](http://localhost:8000) in your browser.
---
## 🧪 Automated Test Suite
Warehouse Autopilot includes automated verification scripts:
```bash
# Verify Startup & Demo Reset 3-Way Dispatch (PO Email + Alert Email + WhatsApp)
python backend/test_startup_demo_dispatch.py
# Verify Twilio Comms Email API (https://comms.twilio.com/v1/Emails)
python backend/test_twilio_email_dispatch.py
# Verify Product QR Intelligence Passport & Reality Check Verification
python backend/test_qr_flow.py
# Verify Settings Persistence Across Resets
python backend/test_reset_and_po.py
```
---
## 📄 License
Distributed under the **MIT License**. See `LICENSE` for more information.
<div align="center">
  <sub>Built with ❤️ for modern, autonomous supply chain operations.</sub>
</div>
