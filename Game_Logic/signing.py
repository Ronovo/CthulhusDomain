"""Signatures on the saves and records the server hands to the browser, so it can tell whether one was edited."""
import hashlib
import hmac
import json
from typing import Any, Dict, Optional

SIGNATURE = "signature"


def _canonical(value: Any) -> Any:
    # The browser re-encodes numbers (5.0 comes back as 5, 1e16 as 10000000000000000), so every number is signed
    # as a float, which both sides read back to the same value.
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return value


class Signer:
    def __init__(self, secret_key: str):
        self._key = hmac.new(secret_key.encode("utf-8"), b"dead-but-dreaming signed data", hashlib.sha256).digest()

    def _signature(self, data: Dict) -> str:
        text = json.dumps(_canonical(data), sort_keys=True, separators=(",", ":"))
        return hmac.new(self._key, text.encode("utf-8"), hashlib.sha256).hexdigest()

    def sign(self, data: Dict) -> Dict:
        return {**data, SIGNATURE: self._signature(data)}

    def verify(self, signed: Any) -> Optional[Dict]:
        """The data without its signature, or None when it is missing, malformed or doesn't match."""
        if not isinstance(signed, dict) or not isinstance(signed.get(SIGNATURE), str):
            return None
        data = {key: value for key, value in signed.items() if key != SIGNATURE}
        try:
            expected = self._signature(data)
        except (TypeError, ValueError):
            return None
        return data if hmac.compare_digest(signed[SIGNATURE], expected) else None
