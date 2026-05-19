import locale
import os
import platform
import subprocess


def _detect_lang() -> str:
    """Return a BCP-47-style language tag for the current system, e.g. 'zh', 'en'."""
    system = platform.system()
    if system == "Darwin":
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleLanguages"],
                capture_output=True, text=True, check=True,
            )
            # Output looks like: (\n    "zh-Hans-CN",\n    "en-US",\n)
            for line in result.stdout.splitlines():
                line = line.strip().strip('",')
                if line and line != "(":
                    return line.split("-")[0].lower()
        except Exception:
            pass

    # Linux / Windows / fallback
    lang = os.environ.get("LANG") or os.environ.get("LANGUAGE") or ""
    if not lang:
        lang = locale.getlocale()[0] or ""
    return lang.split("_")[0].split(".")[0].lower()


_STRINGS = {
    "zh": {
        "title": "Relay: 需要你的确认",
        "suffix": "\n\n请返回终端进行操作。",
    },
    "en": {
        "title": "Relay: Action needs your approval",
        "suffix": "\n\nReturn to your terminal to respond.",
    },
    "ja": {
        "title": "Relay: 操作の確認が必要です",
        "suffix": "\n\nターミナルに戻って操作してください。",
    },
    "ko": {
        "title": "Relay: 작업 확인이 필요합니다",
        "suffix": "\n\n터미널로 돌아가서 작업하세요。",
    },
}

_DEFAULT_LANG = "en"


def _t() -> dict:
    lang = _detect_lang()
    return _STRINGS.get(lang, _STRINGS[_DEFAULT_LANG])


def send_notification(message: str, timeout: int = 30) -> bool:
    s = _t()
    try:
        system = platform.system()
        if system == "Darwin":
            safe_msg = (message + s["suffix"]).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")
            safe_title = s["title"].replace('"', '\\"')
            script = f'display notification "{safe_msg}" with title "{safe_title}"'
            subprocess.Popen(["osascript", "-e", script])
        elif system == "Linux":
            subprocess.run(
                ["notify-send", "--expire-time", str(timeout * 1000), s["title"], message],
                check=True,
                capture_output=True,
            )
        elif system == "Windows":
            from plyer import notification
            notification.notify(title=s["title"], message=message, app_name="Relay", timeout=timeout)
        else:
            return False
        return True
    except Exception:
        return False
