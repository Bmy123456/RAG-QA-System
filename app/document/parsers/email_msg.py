import email
from email.policy import default


def parse_eml(file_path: str) -> str:
    with open(file_path, "rb") as f:
        msg = email.message_from_binary_file(f, policy=default)
    parts = []
    parts.append(f"Subject: {msg['subject']}")
    parts.append(f"From: {msg['from']}")
    parts.append(f"Date: {msg['date']}")
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_content()
                if payload:
                    parts.append(payload)
    else:
        payload = msg.get_content()
        if isinstance(payload, str):
            parts.append(payload)
    return "\n".join(parts)
