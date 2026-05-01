#!/usr/bin/env python3
from __future__ import annotations

import argparse
import email
import imaplib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import Message
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterable


ROOT = Path(__file__).resolve().parent
DEFAULT_QUEUE = ROOT / "data" / "pending_leads.jsonl"
DEFAULT_PROCESSED = ROOT / "data" / "processed_message_ids.txt"
DEFAULT_WHATSAPP_WEBHOOK_LOG = ROOT / "data" / "whatsapp_webhooks.jsonl"
DEFAULT_WHATSAPP_INBOX = ROOT / "data" / "pending_whatsapp.jsonl"
DEFAULT_360DIALOG_BASE_URL = "https://waba-v2.360dialog.io"
DEFAULT_REVIEWER_PHONE = "351913767718"


@dataclass
class LeadDraft:
    created_at: str
    message_id: str
    subject: str
    from_email: str
    lead_name: str
    lead_email: str
    lead_phone: str
    procedure_interest: str
    recommended_channel: str
    status: str
    suggested_reply: str
    raw_excerpt: str


@dataclass
class WhatsAppPendingMessage:
    received_at: str
    message_id: str
    from_phone: str
    profile_name: str
    message_type: str
    text: str
    language: str
    suggested_reply: str
    status: str


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def decode_text(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def message_body(msg: Message) -> str:
    parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition:
                continue
            if content_type not in {"text/plain", "text/html"}:
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if content_type == "text/html":
                text = strip_html(text)
            parts.append(text)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            parts.append(payload.decode(charset, errors="replace"))
    return normalize_space("\n".join(parts))


def strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<br\s*/?>", "\n", html)
    html = re.sub(r"(?s)</p\s*>", "\n", html)
    html = re.sub(r"(?s)<.*?>", " ", html)
    return html


def normalize_space(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def first_match(patterns: Iterable[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I | re.M)
        if match:
            return normalize_space(match.group(1))
    return ""


def extract_phone(text: str) -> str:
    cleaned_text = remove_technical_metadata(text)
    labelled = first_match(
        [
            r"(?:telefone|telem[oó]vel|phone|mobile|contacto|contact)\s*[:\-]\s*([+\d][\d\s().-]{7,})",
            r"(?:whatsapp)\s*[:\-]\s*([+\d][\d\s().-]{7,})",
        ],
        cleaned_text,
    )
    if labelled:
        return clean_phone(labelled)

    # Elementor contact forms often arrive as plain lines:
    # Name / phone / email / message / metadata.
    for line in cleaned_text.splitlines():
        candidate = clean_phone(line)
        digits = re.sub(r"\D", "", candidate)
        if 9 <= len(digits) <= 15 and not looks_like_ip(line):
            return candidate

    match = re.search(r"(\+?\d[\d\s().-]{8,}\d)", cleaned_text)
    return clean_phone(match.group(1)) if match else ""


def remove_technical_metadata(text: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    lines = []
    for line in text.splitlines():
        lower = line.lower().strip()
        if lower.startswith(("remote ip:", "user agent:", "page url:", "powered by:", "date:", "time:")):
            continue
        lines.append(line)
    return "\n".join(lines)


def looks_like_ip(text: str) -> bool:
    return bool(re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text))


def clean_phone(phone: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", phone)
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    return cleaned


def extract_email(text: str, fallback: str) -> str:
    match = re.search(r"[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}", text)
    return match.group(0) if match else fallback


def extract_name(text: str, from_header: str) -> str:
    labelled = first_match(
        [
            r"(?:nome|name)\s*[:\-]\s*([^\n\r]+)",
            r"(?:paciente|patient)\s*[:\-]\s*([^\n\r]+)",
        ],
        text,
    )
    if labelled:
        return labelled
    display = from_header.split("<", 1)[0].strip().strip('"')
    return display if display and "@" not in display else ""


def extract_procedure(text: str, subject: str) -> str:
    labelled = first_match(
        [
            r"(?:procedimento|procedure|tratamento|treatment|interesse|interested in)\s*[:\-]\s*([^\n\r]+)",
            r"(?:mensagem|message)\s*[:\-]\s*([^\n\r]+)",
        ],
        text,
    )
    if labelled:
        return labelled[:160]

    catalog = [
        "deep plane facelift",
        "facelift",
        "neck lift",
        "rinoplastia",
        "rhinoplasty",
        "blefaroplastia",
        "blepharoplasty",
        "brow lift",
        "lip lift",
        "otoplastia",
        "mentoplastia",
        "fat transfer",
    ]
    haystack = f"{subject}\n{text}".lower()
    found = [item for item in catalog if item in haystack]
    return ", ".join(found)


def language_from_text(text: str) -> str:
    lower = text.lower()
    english_hits = ["hello", "dear", "consultation", "procedure", "interested", "appointment"]
    portuguese_hits = ["olá", "ola", "consulta", "procedimento", "gostaria", "marcar"]
    if sum(hit in lower for hit in english_hits) > sum(hit in lower for hit in portuguese_hits):
        return "EN"
    return "PT"


def suggested_reply(name: str, language: str, channel: str) -> str:
    greeting_name = f" {name.split()[0]}" if name else ""
    if language == "EN":
        return (
            f"Hello{greeting_name}! My name is Catia Correia, personal assistant to Dr. Luis Antunes.\n\n"
            "Dr. Antunes would be happy to see you for a consultation to discuss your case. "
            "The consultation can be in person at our clinic in Lisbon or via video call. "
            "The consultation fee is EUR 150.\n\n"
            "Do you have a preference or any specific dates in mind?"
        )
    return (
        f"Olá{greeting_name}! Sou a Cátia Correia, assistente pessoal do Dr. Luís Antunes.\n\n"
        "Podemos agendar uma consulta com o Dr. Antunes para discutir o seu caso. "
        "A consulta pode ser presencial em Lisboa ou por videochamada. O valor é de 150€.\n\n"
        "Tem preferência de datas ou horário?"
    )


def suggested_whatsapp_reply(name: str, text: str, message_type: str) -> str:
    language = language_from_text(text)
    first_name = (name or "").split()[0]
    greeting_name = f" {first_name}" if first_name else ""

    if message_type != "text":
        if language == "EN":
            return (
                f"Hello{greeting_name}, thank you. I will review this with Dr. Antunes "
                "and get back to you as soon as possible."
            )
        return (
            f"Olá{greeting_name}, obrigada. Vou verificar com o Dr. Antunes "
            "e volto a entrar em contacto assim que possível."
        )

    lower = text.lower()
    asks_consult = any(
        hit in lower
        for hit in [
            "consulta",
            "marcar",
            "agendar",
            "appointment",
            "consultation",
            "schedule",
            "book",
        ]
    )
    if asks_consult:
        return suggested_reply(name, language, "WhatsApp")

    if language == "EN":
        return (
            f"Hello{greeting_name}, thank you for your message. "
            "I will check this and get back to you shortly."
        )
    return (
        f"Olá{greeting_name}, obrigada pela sua mensagem. "
        "Vou verificar e volto a entrar em contacto em breve."
    )


def whatsapp_phone(phone: str) -> str:
    cleaned = clean_phone(phone)
    digits = re.sub(r"\D", "", cleaned)
    if not digits:
        return ""
    if cleaned.startswith("+"):
        return digits
    if digits.startswith("00"):
        return digits[2:]
    if len(digits) == 9 and digits.startswith("9"):
        return f"351{digits}"
    return digits


def build_lead_draft(msg: Message) -> LeadDraft:
    subject = decode_text(msg.get("Subject"))
    from_header = decode_text(msg.get("From"))
    from_email = extract_email(from_header, "")
    body = message_body(msg)
    lead_email = extract_email(body, from_email)
    lead_phone = extract_phone(body)
    lead_name = extract_name(body, from_header)
    language = language_from_text(f"{subject}\n{body}")
    channel = "WhatsApp" if lead_phone else "Email"
    procedure = extract_procedure(body, subject)
    message_id = msg.get("Message-ID") or f"{from_email}:{subject}:{msg.get('Date')}"

    return LeadDraft(
        created_at=datetime.now(timezone.utc).isoformat(),
        message_id=message_id,
        subject=subject,
        from_email=from_email,
        lead_name=lead_name,
        lead_email=lead_email,
        lead_phone=lead_phone,
        procedure_interest=procedure,
        recommended_channel=channel,
        status="Aguardando resposta",
        suggested_reply=suggested_reply(lead_name, language, channel),
        raw_excerpt=body[:1200],
    )


def read_processed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def append_processed(path: Path, ids: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for message_id in ids:
            handle.write(message_id.replace("\n", " ") + "\n")


def append_queue(path: Path, drafts: Iterable[LeadDraft]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for draft in drafts:
            handle.write(json.dumps(asdict(draft), ensure_ascii=False) + "\n")


def append_whatsapp_inbox(path: Path, messages: Iterable[WhatsAppPendingMessage]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for message in messages:
            handle.write(json.dumps(asdict(message), ensure_ascii=False) + "\n")


def fetch(limit: int) -> None:
    load_env_file(ROOT / ".env")
    queue_path = Path(env("LEAD_QUEUE_PATH", str(DEFAULT_QUEUE)))
    processed_path = Path(env("PROCESSED_IDS_PATH", str(DEFAULT_PROCESSED)))
    processed = read_processed(processed_path)

    host = env("IMAP_HOST")
    port = int(env("IMAP_PORT", "993"))
    user = env("IMAP_USER")
    password = env("IMAP_PASSWORD")
    folder = env("IMAP_FOLDER", "INBOX")

    if not all([host, user, password]):
        raise SystemExit("Configurar IMAP_HOST, IMAP_USER e IMAP_PASSWORD em lead_agent/.env")

    drafts: list[LeadDraft] = []
    new_processed: list[str] = []
    with imaplib.IMAP4_SSL(host, port) as client:
        client.login(user, password)
        client.select(folder)
        status, data = client.search(None, "UNSEEN")
        if status != "OK":
            raise SystemExit("Nao foi possivel pesquisar emails.")
        ids = data[0].split()[-limit:]
        for uid in ids:
            status, msg_data = client.fetch(uid, "(RFC822)")
            if status != "OK" or not msg_data:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            draft = build_lead_draft(msg)
            if draft.message_id in processed:
                continue
            drafts.append(draft)
            new_processed.append(draft.message_id)

    append_queue(queue_path, drafts)
    append_processed(processed_path, new_processed)
    print(f"Novas leads adicionadas a fila: {len(drafts)}")
    print(f"Fila: {queue_path}")


def show() -> None:
    load_env_file(ROOT / ".env")
    queue_path = Path(env("LEAD_QUEUE_PATH", str(DEFAULT_QUEUE)))
    if not queue_path.exists():
        print("Fila vazia.")
        return
    for index, line in enumerate(queue_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        print(f"\n#{index} {item.get('lead_name') or '(sem nome)'} | {item.get('recommended_channel')} | {item.get('procedure_interest')}")
        print(f"Telefone: {item.get('lead_phone') or '-'}")
        print(f"Email: {item.get('lead_email') or '-'}")
        print(f"Assunto: {item.get('subject')}")
        print("Resposta sugerida:")
        print(item.get("suggested_reply", ""))


def load_queue() -> list[dict]:
    load_env_file(ROOT / ".env")
    queue_path = Path(env("LEAD_QUEUE_PATH", str(DEFAULT_QUEUE)))
    if not queue_path.exists():
        return []
    return [
        json.loads(line)
        for line in queue_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def open_url(url: str) -> None:
    if sys.platform == "darwin":
        attempts = [
            ["open", "-a", "/Applications/Safari.app", url],
            ["open", "-a", "/Applications/Google Chrome.app", url],
            ["open", "-a", "/Applications/Brave Browser.app", url],
            ["open", url],
        ]
        for command in attempts:
            try:
                subprocess.run(command, check=True)
                return
            except subprocess.CalledProcessError:
                continue
        subprocess.run("pbcopy", input=url.encode("utf-8"), check=False)
        raise SystemExit("Nao consegui abrir o browser automaticamente. Copiei o link para a area de transferencia.")
    elif os.name == "nt":
        subprocess.run(["cmd", "/c", "start", "", url], check=True)
    else:
        subprocess.run(["xdg-open", url], check=True)


def whatsapp(index: int, open_browser: bool) -> None:
    items = load_queue()
    if not items:
        raise SystemExit("Fila vazia.")
    if index < 1 or index > len(items):
        raise SystemExit(f"Indice invalido. Existem {len(items)} leads na fila.")

    item = items[index - 1]
    phone = whatsapp_phone(item.get("lead_phone", ""))
    if not phone:
        raise SystemExit("Esta lead nao tem telefone valido para WhatsApp.")

    message = item.get("suggested_reply", "")
    url = f"https://web.whatsapp.com/send?phone={phone}&text={urllib.parse.quote(message)}"
    print(url)
    if open_browser:
        open_url(url)


def whatsapp_api_url(path: str) -> str:
    version = env("WHATSAPP_API_VERSION", "v20.0").strip().lstrip("/")
    return f"https://graph.facebook.com/{version}/{path.lstrip('/')}"


def whatsapp_api_request(payload: dict) -> dict:
    provider = env("WHATSAPP_PROVIDER", "meta").strip().lower()
    if provider in {"360dialog", "360", "d360"}:
        return whatsapp_360dialog_request("/messages", payload)

    token = env("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = env("WHATSAPP_PHONE_NUMBER_ID")
    if not token or not phone_number_id:
        raise SystemExit("Configurar WHATSAPP_ACCESS_TOKEN e WHATSAPP_PHONE_NUMBER_ID em lead_agent/.env")

    url = whatsapp_api_url(f"{phone_number_id}/messages")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Erro WhatsApp API {error.code}: {details}") from error


def whatsapp_360dialog_url(path: str) -> str:
    base_url = env("D360_BASE_URL", DEFAULT_360DIALOG_BASE_URL).rstrip("/")
    return f"{base_url}/{path.lstrip('/')}"


def whatsapp_360dialog_request(path: str, payload: dict | None = None, method: str = "POST") -> dict:
    api_key = env("D360_API_KEY")
    if not api_key:
        raise SystemExit("Configurar D360_API_KEY em lead_agent/.env")

    data = None
    headers = {
        "D360-API-KEY": api_key,
        "Accept": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        whatsapp_360dialog_url(path),
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Erro 360dialog API {error.code}: {details}") from error


def whatsapp_text_payload(phone: str, body: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": body,
        },
    }


def whatsapp_api_check() -> None:
    load_env_file(ROOT / ".env")
    provider = env("WHATSAPP_PROVIDER", "meta").strip().lower()
    if provider in {"360dialog", "360", "d360"}:
        required = ["D360_API_KEY", "D360_BASE_URL", "WHATSAPP_VERIFY_TOKEN"]
        label = "360dialog WhatsApp API config"
    else:
        required = [
            "WHATSAPP_ACCESS_TOKEN",
            "WHATSAPP_PHONE_NUMBER_ID",
            "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "WHATSAPP_VERIFY_TOKEN",
        ]
        label = "WhatsApp Cloud API config"
    missing = []
    placeholder = []
    for key in required:
        value = env(key)
        if not value:
            missing.append(key)
        elif "COLOCAR" in value or "colocar" in value:
            placeholder.append(key)

    print(label)
    print(f"- WHATSAPP_PROVIDER: {provider or 'meta'}")
    for key in required:
        value = env(key)
        if not value:
            status = "em falta"
        elif key == "WHATSAPP_VERIFY_TOKEN":
            status = "configurado"
        elif "COLOCAR" in value or "colocar" in value:
            status = "placeholder"
        else:
            status = "configurado"
        print(f"- {key}: {status}")

    if missing or placeholder:
        raise SystemExit("Configuracao incompleta. Preencher os campos em falta no lead_agent/.env.")

    print("Configuracao minima preenchida.")


def whatsapp_set_webhook(url: str, confirm: bool) -> None:
    load_env_file(ROOT / ".env")
    provider = env("WHATSAPP_PROVIDER", "meta").strip().lower()
    if provider not in {"360dialog", "360", "d360"}:
        raise SystemExit("Este comando configura webhooks apenas para 360dialog. Definir WHATSAPP_PROVIDER=360dialog.")

    payload = {"url": url}
    if not confirm:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("\nDry-run: nada foi configurado. Para configurar, repetir com --confirm.")
        return

    result = whatsapp_360dialog_request("/v1/configs/webhook", payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def whatsapp_send_text(index: int, confirm: bool) -> None:
    load_env_file(ROOT / ".env")
    items = load_queue()
    if not items:
        raise SystemExit("Fila vazia.")
    if index < 1 or index > len(items):
        raise SystemExit(f"Indice invalido. Existem {len(items)} leads na fila.")

    item = items[index - 1]
    phone = whatsapp_phone(item.get("lead_phone", ""))
    if not phone:
        raise SystemExit("Esta lead nao tem telefone valido para WhatsApp.")

    payload = whatsapp_text_payload(phone, item.get("suggested_reply", ""))

    if not confirm:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("\nDry-run: nada foi enviado. Para enviar, repetir com --confirm.")
        return

    result = whatsapp_api_request(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def whatsapp_send_template(index: int, template_name: str, language_code: str, confirm: bool) -> None:
    load_env_file(ROOT / ".env")
    items = load_queue()
    if not items:
        raise SystemExit("Fila vazia.")
    if index < 1 or index > len(items):
        raise SystemExit(f"Indice invalido. Existem {len(items)} leads na fila.")

    item = items[index - 1]
    phone = whatsapp_phone(item.get("lead_phone", ""))
    first_name = (item.get("lead_name") or "").split()[0] or "Olá"
    if not phone:
        raise SystemExit("Esta lead nao tem telefone valido para WhatsApp.")

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": first_name},
                    ],
                }
            ],
        },
    }

    if not confirm:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("\nDry-run: nada foi enviado. Para enviar, repetir com --confirm.")
        return

    result = whatsapp_api_request(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))


class WhatsAppWebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        load_env_file(ROOT / ".env")
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"", "/", "/health"}:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            return

        params = urllib.parse.parse_qs(parsed.query)
        mode = params.get("hub.mode", [""])[0]
        token = params.get("hub.verify_token", [""])[0]
        challenge = params.get("hub.challenge", [""])[0]
        expected = env("WHATSAPP_VERIFY_TOKEN")

        if mode == "subscribe" and expected and token == expected:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(challenge.encode("utf-8"))
            return

        self.send_response(403)
        self.end_headers()
        self.wfile.write(b"Forbidden")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        log_path = Path(env("WHATSAPP_WEBHOOK_LOG", str(DEFAULT_WHATSAPP_WEBHOOK_LOG)))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "received_at": datetime.now(timezone.utc).isoformat(),
            "headers": dict(self.headers),
            "body": json.loads(body) if body else {},
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

        pending = extract_pending_whatsapp_messages(event["body"], event["received_at"])
        inbox_path = Path(env("WHATSAPP_INBOX_PATH", str(DEFAULT_WHATSAPP_INBOX)))
        append_whatsapp_inbox(inbox_path, pending)
        notify_reviewer(pending)
        print_webhook_summary(event["body"])

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format: str, *args) -> None:
        return


def print_webhook_summary(body: dict) -> None:
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            field = change.get("field", "")
            value = change.get("value", {})
            for message in value.get("messages", []):
                sender = message.get("from", "-")
                message_type = message.get("type", "-")
                if message_type == "text":
                    content = message.get("text", {}).get("body", "")
                elif message_type in {"image", "document", "audio", "video"}:
                    content = message.get(message_type, {}).get("filename") or message_type
                else:
                    content = message_type
                print(f"[webhook] {field} | {sender} | {message_type}: {content}", flush=True)


def extract_pending_whatsapp_messages(body: dict, received_at: str) -> list[WhatsAppPendingMessage]:
    pending: list[WhatsAppPendingMessage] = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            value = change.get("value", {})
            contact_names = {
                contact.get("wa_id", ""): contact.get("profile", {}).get("name", "")
                for contact in value.get("contacts", [])
            }
            for message in value.get("messages", []):
                message_type = message.get("type", "")
                sender = message.get("from", "")
                text = ""
                if message_type == "text":
                    text = message.get("text", {}).get("body", "")
                elif message_type in {"image", "document", "audio", "video"}:
                    text = message.get(message_type, {}).get("filename") or f"[{message_type}]"
                else:
                    text = f"[{message_type or 'mensagem'}]"

                profile_name = contact_names.get(sender, "")
                language = language_from_text(text)
                pending.append(
                    WhatsAppPendingMessage(
                        received_at=received_at,
                        message_id=message.get("id", ""),
                        from_phone=sender,
                        profile_name=profile_name,
                        message_type=message_type,
                        text=text,
                        language=language,
                        suggested_reply=suggested_whatsapp_reply(profile_name, text, message_type),
                        status="Aguardando validação",
                    )
                )
    return pending


def show_whatsapp_inbox(limit: int) -> None:
    load_env_file(ROOT / ".env")
    inbox_path = Path(env("WHATSAPP_INBOX_PATH", str(DEFAULT_WHATSAPP_INBOX)))
    if not inbox_path.exists():
        print("Fila WhatsApp vazia.")
        return
    rows = [
        json.loads(line)
        for line in inbox_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for index, item in enumerate(rows[-limit:], start=max(1, len(rows) - limit + 1)):
        print(f"\n#{index} {item.get('profile_name') or '(sem nome)'} | {item.get('from_phone')} | {item.get('message_type')}")
        print(f"Mensagem: {item.get('text')}")
        print("Resposta sugerida:")
        print(item.get("suggested_reply", ""))


def reviewer_phone() -> str:
    return whatsapp_phone(env("REVIEWER_WHATSAPP", DEFAULT_REVIEWER_PHONE))


def notify_reviewer(messages: list[WhatsAppPendingMessage]) -> None:
    reviewer = reviewer_phone()
    if not reviewer:
        return

    clinic_number = whatsapp_phone(env("WHATSAPP_CLINIC_NUMBER", "351938336026"))
    for message in messages:
        if whatsapp_phone(message.from_phone) == reviewer:
            continue
        if clinic_number and whatsapp_phone(message.from_phone) == clinic_number:
            continue

        review_text = format_review_message(message)
        try:
            whatsapp_api_request(whatsapp_text_payload(reviewer, review_text))
            print(f"[review] enviado para {reviewer}: {message.from_phone}", flush=True)
        except SystemExit as error:
            print(f"[review] erro ao enviar para {reviewer}: {error}", flush=True)


def format_review_message(message: WhatsAppPendingMessage) -> str:
    patient = message.profile_name or "(sem nome)"
    return (
        "Nova mensagem WhatsApp para validar\n\n"
        f"Paciente: {patient}\n"
        f"Telefone: +{message.from_phone}\n"
        f"Mensagem:\n{message.text}\n\n"
        "Sugestão de resposta:\n"
        f"{message.suggested_reply}\n\n"
        "Por agora esta mensagem é só para validação. "
        "O agente ainda não respondeu automaticamente ao paciente."
    )


def webhook_server(host: str, port: int) -> None:
    load_env_file(ROOT / ".env")
    server = HTTPServer((host, port), WhatsAppWebhookHandler)
    print(f"Webhook WhatsApp a escutar em http://{host}:{port}/webhook")
    print("Para producao, este endpoint tem de estar publico via dominio/HTTPS.")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente de leads Dr. Luis Antunes")
    sub = parser.add_subparsers(dest="cmd", required=True)
    fetch_parser = sub.add_parser("fetch", help="Ler emails nao lidos e criar fila de revisao")
    fetch_parser.add_argument("--limit", type=int, default=20)
    sub.add_parser("show", help="Mostrar fila de revisao")
    inbox_parser = sub.add_parser("whatsapp-inbox", help="Mostrar mensagens WhatsApp pendentes")
    inbox_parser.add_argument("--limit", type=int, default=20)
    whatsapp_parser = sub.add_parser("whatsapp", help="Abrir WhatsApp Web com uma lead da fila")
    whatsapp_parser.add_argument("index", type=int, help="Numero da lead na fila, como mostrado por show")
    whatsapp_parser.add_argument("--no-open", action="store_true", help="So mostrar o link, sem abrir o browser")
    api_send_parser = sub.add_parser("api-send", help="Enviar mensagem livre pela WhatsApp Cloud API")
    api_send_parser.add_argument("index", type=int, help="Numero da lead na fila")
    api_send_parser.add_argument("--confirm", action="store_true", help="Enviar de verdade")
    sub.add_parser("api-check", help="Verificar configuracao da API WhatsApp")
    webhook_set_parser = sub.add_parser("api-set-webhook", help="Configurar webhook na 360dialog")
    webhook_set_parser.add_argument("url", help="URL publico HTTPS do webhook")
    webhook_set_parser.add_argument("--confirm", action="store_true", help="Configurar de verdade")
    template_parser = sub.add_parser("api-template", help="Enviar template aprovado pela WhatsApp Cloud API")
    template_parser.add_argument("index", type=int, help="Numero da lead na fila")
    template_parser.add_argument("--template", required=True, help="Nome do template aprovado na Meta")
    template_parser.add_argument("--language", default="pt_PT", help="Codigo de idioma do template, ex: pt_PT ou en_US")
    template_parser.add_argument("--confirm", action="store_true", help="Enviar de verdade")
    webhook_parser = sub.add_parser("webhook", help="Servidor local para webhook WhatsApp")
    webhook_parser.add_argument("--host", default="127.0.0.1")
    webhook_parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    args = parser.parse_args()

    if args.cmd == "fetch":
        fetch(args.limit)
    elif args.cmd == "show":
        show()
    elif args.cmd == "whatsapp-inbox":
        show_whatsapp_inbox(args.limit)
    elif args.cmd == "whatsapp":
        whatsapp(args.index, open_browser=not args.no_open)
    elif args.cmd == "api-send":
        whatsapp_send_text(args.index, confirm=args.confirm)
    elif args.cmd == "api-check":
        whatsapp_api_check()
    elif args.cmd == "api-set-webhook":
        whatsapp_set_webhook(args.url, confirm=args.confirm)
    elif args.cmd == "api-template":
        whatsapp_send_template(args.index, args.template, args.language, confirm=args.confirm)
    elif args.cmd == "webhook":
        webhook_server(args.host, args.port)


if __name__ == "__main__":
    main()
