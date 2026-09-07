from __future__ import annotations

import json
from pathlib import Path

from dragon.whatsapp import (
    DisabledWhatsAppProvider,
    MetaWhatsAppProvider,
    WhatsAppError,
    whatsapp_provider_from_config,
)


def test_provider_stays_unavailable_until_integration_is_proven() -> None:
    config = {
        "providers": {
            "whatsapp": {
                "enabled": True,
                "type": "meta-cloud-api",
                "integration_test_status": "NOT_RUN",
                "graph_version": "v99.0",
            }
        }
    }
    assert isinstance(whatsapp_provider_from_config(config, {}), DisabledWhatsAppProvider)


def test_meta_provider_uploads_pdf_and_records_redacted_acceptance(tmp_path: Path) -> None:
    calls = []

    def request(method: str, url: str, headers: dict[str, str], body: bytes) -> dict:
        calls.append((method, url, headers, body))
        if url.endswith("/media"):
            return {"id": "media-123"}
        payload = json.loads(body.decode("utf-8"))
        return {"messages": [{"id": f"wamid-{payload['to'][-2:]}", "message_status": "accepted"}]}

    pdf = tmp_path / "DRAGON-2099-01-02.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfixture")
    provider = MetaWhatsAppProvider(
        graph_version="v99.0",
        phone_number_id="phone-id",
        access_token="secret-token",
        recipients=("212600000001", "212600000002"),
        request=request,
    )

    receipt = provider.send(pdf, "2099-01-02")

    assert receipt["status"] == "COMPLETE"
    assert receipt["accepted"] is True
    assert len(receipt["recipients"]) == 2
    serialized = json.dumps(receipt)
    assert "212600000001" not in serialized
    assert "secret-token" not in serialized
    assert calls[0][1].endswith("/v99.0/phone-id/media")
    assert calls[1][1].endswith("/v99.0/phone-id/messages")
    assert b'"type": "document"' in calls[1][3]


def test_partial_retry_does_not_resend_an_accepted_recipient(tmp_path: Path) -> None:
    calls = []
    fail_second = [True]

    def request(method: str, url: str, headers: dict[str, str], body: bytes) -> dict:
        if url.endswith("/media"):
            calls.append("upload")
            return {"id": "media-123"}
        recipient = json.loads(body.decode("utf-8"))["to"]
        calls.append(recipient)
        if recipient.endswith("02") and fail_second[0]:
            raise WhatsAppError("injected send failure")
        return {"messages": [{"id": f"wamid-{recipient[-2:]}"}]}

    pdf = tmp_path / "edition.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfixture")
    provider = MetaWhatsAppProvider(
        "v99.0",
        "phone-id",
        "token",
        ("212600000001", "212600000002"),
        request=request,
    )
    try:
        provider.send(pdf, "2099-01-02")
    except WhatsAppError as exc:
        partial = exc.partial_receipt
    else:
        raise AssertionError("injected failure did not occur")
    assert partial is not None
    assert [item["message_id"] for item in partial["recipients"]] == ["wamid-01"]

    fail_second[0] = False
    result = provider.send(pdf, "2099-01-02", partial)

    assert result["status"] == "COMPLETE"
    assert calls == ["upload", "212600000001", "212600000002", "212600000002"]
