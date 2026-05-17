import platform
import subprocess


def send_notification(title: str, message: str, timeout: int = 10) -> bool:
    try:
        system = platform.system()
        if system == "Darwin":
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        elif system == "Linux":
            subprocess.run(
                ["notify-send", "--expire-time", str(timeout * 1000), title, message],
                check=True,
                capture_output=True,
            )
        elif system == "Windows":
            from plyer import notification
            notification.notify(title=title, message=message, app_name="Relay", timeout=timeout)
        else:
            return False
        return True
    except Exception:
        return False
