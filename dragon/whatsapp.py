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

    def __init__(self, detail: str, *, partial_receipt: dict | None = None):
        super().__init__(detail)
        self.partial_receipt = partial_receipt


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

    def send(
        self,
        pdf: Path,
        edition_date: str,
        prior_receipt: dict | None = None,
        lead_headlines: tuple[str, ...] = (),
    ) -> dict:
        return {"status": "DEGRADED", "reason": self.reason, "accepted": False}


@dataclass(frozen=True)
class MetaWhatsAppProvider:
    graph_version: str
    phone_number_id: str
    access_token: str
    recipients: tuple[str, ...]
    request: HttpRequest = _request
    archive_link_template: str = ""
    enabled: bool = True

    def send(
        self,
        pdf: Path,
        edition_date: str,
        prior_receipt: dict | None = None,
        lead_headlines: tuple[str, ...] = (),
    ) -> dict:
        if not pdf.is_file() or pdf.suffix.casefold() != ".pdf":
            raise WhatsAppError("canonical PDF is missing or invalid")
        if pdf.stat().st_size > 100 * 1024 * 1024:
            raise WhatsAppError("PDF exceeds the 100 MB document limit")
        if not self.recipients:
            raise WhatsAppError("no recipients configured")
        pdf_hash = sha256_file(pdf)
        caption_lines = [f"اكتمل نشر صحيفة DRAGON — {edition_date}"]
        caption_lines.extend(f"• {headline.strip()}" for headline in lead_headlines[:3] if headline.strip())
        archive_link = ""
        if self.archive_link_template:
            try:
                archive_link = self.archive_link_template.format(date=edition_date)
            except (KeyError, ValueError) as exc:
                raise WhatsAppError("archive link template is invalid") from exc
            if archive_link:
                caption_lines.append(f"الأرشيف: {archive_link}")
        caption = "\n".join(caption_lines)
        if len(caption) > 1024:
            raise WhatsAppError("delivery caption exceeds the provider limit")
        delivery_fingerprint = hashlib.sha256(
            f"{pdf_hash}\n{edition_date}\n{caption}".encode("utf-8")
        ).hexdigest()
        base = f"https://graph.facebook.com/{self.graph_version}/{self.phone_number_id}"
        authorization = {"Authorization": f"Bearer {self.access_token}"}
        prior = prior_receipt or {}
        if (
            prior.get("delivery_fingerprint") == delivery_fingerprint
            and isinstance(prior.get("media_id"), str)
        ):
            media_id = prior["media_id"]
            accepted = list(prior.get("recipients", []))
        else:
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
        accepted_hashes = {
            item.get("recipient_hash") for item in accepted if isinstance(item, dict)
        }
        for recipient in self.recipients:
            recipient_hash = hashlib.sha256(recipient.encode()).hexdigest()[:16]
            if recipient_hash in accepted_hashes:
                continue
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "document",
                "document": {
                    "id": media_id,
                    "caption": caption,
                    "filename": pdf.name,
                },
            }
            try:
                response = self.request(
                    "POST",
                    f"{base}/messages",
                    {**authorization, "Content-Type": "application/json"},
                    json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                )
            except WhatsAppError as exc:
                partial = self._receipt(
                    pdf_hash,
                    media_id,
                    accepted,
                    complete=False,
                    delivery_fingerprint=delivery_fingerprint,
                    edition_date=edition_date,
                    headline_count=min(len(lead_headlines), 3),
                    archive_link=archive_link,
                )
                raise WhatsAppError(str(exc), partial_receipt=partial) from exc
            messages = response.get("messages")
            message_id = messages[0].get("id") if isinstance(messages, list) and messages and isinstance(messages[0], dict) else None
            if not isinstance(message_id, str) or not message_id:
                raise WhatsAppError("send response has no message id")
            accepted.append(
                {
                    "recipient_hash": recipient_hash,
                    "message_id": message_id,
                    "status": "ACCEPTED_BY_PROVIDER",
                }
            )
        return self._receipt(
            pdf_hash,
            media_id,
            accepted,
            complete=True,
            delivery_fingerprint=delivery_fingerprint,
            edition_date=edition_date,
            headline_count=min(len(lead_headlines), 3),
            archive_link=archive_link,
        )

    def _receipt(
        self,
        pdf_hash: str,
        media_id: str,
        accepted: list[dict],
        *,
        complete: bool,
        delivery_fingerprint: str,
        edition_date: str,
        headline_count: int,
        archive_link: str,
    ) -> dict:
        return {
            "status": "COMPLETE" if complete else "FAILED_PARTIAL",
            "accepted": complete,
            "provider": "meta-cloud-api",
            "media_id": media_id,
            "pdf_sha256": pdf_hash,
            "delivery_fingerprint": delivery_fingerprint,
            "edition_date": edition_date,
            "publication_status": "COMPLETE",
            "lead_headline_count": headline_count,
            "archive_link": archive_link or None,
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
    return MetaWhatsAppProvider(
        version,
        phone,
        token,
        recipients,
        archive_link_template=str(value.get("archive_link_template", "")),
    )
