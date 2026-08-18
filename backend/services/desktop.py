"""Desktop notification service.

Triggers native Windows desktop toast notifications asynchronously from Python,
ensuring managers are immediately alerted to critical warehouse events even
when the browser window is minimized or in the background.
"""
import os
import subprocess
import threading
from ..db import get_setting, env_or_setting
from ..events import hub


def _bool(v) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")


def _send_windows_toast(title: str, message: str, severity: str = "INFO"):
    """Background execution of native Windows Toast using PowerShell WinRT API."""
    clean_title = (title or "Warehouse Alert").replace("'", "''").replace("\n", " ")
    clean_msg = (message or "").replace("'", "''").replace("\n", " ")
    if len(clean_msg) > 180:
        clean_msg = clean_msg[:177] + "..."

    ps_cmd = f"""
    $ErrorActionPreference = 'SilentlyContinue'
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $textNodes = $template.GetElementsByTagName("text")
    $textNodes.Item(0).AppendChild($template.CreateTextNode('{clean_title}')) > $null
    $textNodes.Item(1).AppendChild($template.CreateTextNode('{clean_msg}')) > $null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Warehouse Autopilot").Show($toast)
    """

    try:
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def send_desktop_notification(title: str, message: str, severity: str = "INFO") -> bool:
    """Send desktop notification if enabled. Non-blocking."""
    enabled = _bool(env_or_setting("DESKTOP_NOTIFICATIONS_ENABLED", "desktop_notifications_enabled", "true"))
    if not enabled:
        return False

    # 1. Dispatch native OS toast in background thread
    threading.Thread(target=_send_windows_toast, args=(title, message, severity), daemon=True).start()

    # 2. Also publish over SSE for browser instant toast
    hub.publish("desktop_notification", {
        "title": title,
        "message": message,
        "severity": severity,
    })
    return True
