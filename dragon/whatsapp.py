"""Opt-in Meta WhatsApp Cloud API document delivery provider."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import mimetypes
import os
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from dragon.state import sha256_file


class WhatsAppError(RuntimeError):
    code = "WHATSAPP_SEND_FAILED"


HttpRequest = Callable[[str, str, dict[str, str], bytes], dict]


def _request(method: str, url: str, headers: dict[str, str], body: bytes) -> dict:
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=60) as response:
            payload = response.read()
    except HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", "replace")
        raise WhatsAppError(f"Meta HTTP {exc.code}: {detail}") from exc
    except (OSError, URLError) as exc:
        raise WhatsAppError(str(exc)) from exc
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WhatsAppError("Meta returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise WhatsAppError("Meta returned a non-object response")
    return value


def _multipart_pdf(path: Path) -> tuple[bytes, str]:
    boundary = f"dragon-{uuid4().hex}"
    filename = path.name.replace('"', "")
    content_type = mimetypes.guess_type(filename)[0] or "application/pdf"
    chunks = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"messaging_product\"\r\n\r\nwhatsapp\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n".encode(),
        path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks), boundary


@dataclass(frozen=True)
class DisabledWhatsAppProvider:
    reason: str = "PROVIDER_DISABLED_OR_UNCONFIGURED"
    enabled: bool = False

    def send(self, pdf: Path, edition_date: str) -> dict:
        return {"status": "DEGRADED", "reason": self.reason, "accepted": False}


@dataclass(frozen=True)
class MetaWhatsAppProvider:
    graph_version: str
    phone_number_id: str
    access_token: str
    recipients: tuple[str, ...]
    request: HttpRequest = _request
    enabled: bool = True

    def send(self, pdf: Path, edition_date: str) -> dict:
        if not pdf.is_file() or pdf.suffix.casefold() != ".pdf":
            raise WhatsAppError("canonical PDF is missing or invalid")
        if pdf.stat().st_size > 100 * 1024 * 1024:
            raise WhatsAppError("PDF exceeds the 100 MB document limit")
        if not self.recipients:
            raise WhatsAppError("no recipients configured")
        base = f"https://graph.facebook.com/{self.graph_version}/{self.phone_number_id}"
        authorization = {"Authorization": f"Bearer {self.access_token}"}
        upload_body, boundary = _multipart_pdf(pdf)
        upload = self.request(
            "POST",
            f"{base}/media",
            {**authorization, "Content-Type": f"multipart/form-data; boundary={boundary}"},
            upload_body,
        )
        media_id = upload.get("id")
        if not isinstance(media_id, str) or not media_id:
            raise WhatsAppError("media upload response has no id")
        accepted = []
        for recipient in self.recipients:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "document",
                "document": {
                    "id": media_id,
                    "caption": f"صحيفة DRAGON — {edition_date}",
                    "filename": pdf.name,
                },
            }
            response = self.request(
                "POST",
                f"{base}/messages",
                {**authorization, "Content-Type": "application/json"},
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )
            messages = response.get("messages")
            message_id = messages[0].get("id") if isinstance(messages, list) and messages and isinstance(messages[0], dict) else None
            if not isinstance(message_id, str) or not message_id:
                raise WhatsAppError("send response has no message id")
            accepted.append(
                {
                    "recipient_hash": hashlib.sha256(recipient.encode()).hexdigest()[:16],
                    "message_id": message_id,
                    "status": "ACCEPTED_BY_PROVIDER",
                }
            )
        return {
            "status": "COMPLETE",
            "accepted": True,
            "provider": "meta-cloud-api",
            "media_id": media_id,
            "pdf_sha256": sha256_file(pdf),
            "recipients": accepted,
            "delivery_evidence": "API_ACCEPTANCE; final device delivery requires webhook evidence",
        }


def whatsapp_provider_from_config(config: dict, environ: dict[str, str] | None = None):
    value = config.get("providers", {}).get("whatsapp", {})
    if not value.get("enabled"):
        return DisabledWhatsAppProvider()
    if value.get("type") != "meta-cloud-api":
        return DisabledWhatsAppProvider("PROVIDER_TYPE_UNSUPPORTED")
    if value.get("integration_test_status") != "PASS":
        return DisabledWhatsAppProvider("PROVIDER_INTEGRATION_NOT_PROVEN")
    environment = os.environ if environ is None else environ
    token = environment.get(str(value.get("access_token_env", "META_WHATSAPP_ACCESS_TOKEN")), "")
    phone = environment.get(str(value.get("phone_number_id_env", "META_WHATSAPP_PHONE_NUMBER_ID")), "")
    raw_recipients = environment.get(str(value.get("recipients_env", "DRAGON_WHATSAPP_RECIPIENTS")), "")
    recipients = tuple(item.strip() for item in raw_recipients.split(",") if item.strip())
    version = str(value.get("graph_version", ""))
    if not token or not phone or not recipients or not version:
        return DisabledWhatsAppProvider("PROVIDER_CONFIGURATION_INCOMPLETE")
    return MetaWhatsAppProvider(version, phone, token, recipients)
