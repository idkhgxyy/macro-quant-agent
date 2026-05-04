import json
import urllib.request


def post_json(url: str, payload: dict, timeout_s: float = 5.0) -> tuple[bool, str]:
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url=url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=float(timeout_s)) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            return True, body[:500]
    except Exception as e:
        return False, str(e)

