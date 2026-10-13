"""Local auth API with a loopback SMTP capture; never delivers external email."""

import json
import os
import socketserver
import sys
import threading
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", os.environ.get("E2E_DATABASE_URL", ""))
os.environ.setdefault("SECRET_KEY", "local-auth-only-secret-at-least-32-characters")
os.environ.setdefault("ENVIRONMENT", "test")

from api.app.config import Settings
from api.app.main import create_app


class MailCapture(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        self.connection.settimeout(15)
        self.wfile.write(b"220 localhost SMTP capture\r\n")
        while line := self.rfile.readline(8192):
            command = line.split(b" ", 1)[0].strip().upper()
            if command in {b"EHLO", b"HELO"}:
                self.wfile.write(b"250 localhost\r\n")
            elif command in {b"MAIL", b"RCPT", b"RSET", b"NOOP"}:
                self.wfile.write(b"250 OK\r\n")
            elif command == b"DATA":
                self.wfile.write(b"354 End with dot\r\n")
                lines = []
                while chunk := self.rfile.readline(8192):
                    if chunk == b".\r\n":
                        break
                    lines.append(chunk[1:] if chunk.startswith(b"..") else chunk)
                message = BytesParser(policy=policy.default).parsebytes(b"".join(lines))
                body = message.get_body(preferencelist=("plain",))
                payload = {
                    "recipient": str(message["To"]),
                    "subject": str(message["Subject"]),
                    "text": body.get_content() if body else "",
                }
                mailbox = Path(os.environ["E2E_MAILBOX_DIR"])
                target = mailbox / f"{uuid4()}.json"
                with target.open("x", encoding="utf-8") as output:
                    os.chmod(target, 0o600)
                    json.dump(payload, output)
                self.wfile.write(b"250 Captured locally\r\n")
            elif command == b"QUIT":
                self.wfile.write(b"221 Bye\r\n")
                break
            else:
                self.wfile.write(b"502 Unsupported command\r\n")


def main() -> None:
    database_url = os.environ["E2E_DATABASE_URL"]
    if not urlsplit(database_url).path.endswith("_test"):
        raise SystemExit("Auth acceptance requires a disposable database ending in _test")
    mailbox = Path(os.environ["E2E_MAILBOX_DIR"])
    mailbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    settings = Settings(
        environment="test",
        database_url=database_url,
        secret_key="local-auth-only-secret-at-least-32-characters",
        cors_origins="http://127.0.0.1:5178",
        project_invitation_url="http://127.0.0.1:5178/project-invitations",
        password_reset_url="http://127.0.0.1:5178/reset-password",
        email_verification_url="http://127.0.0.1:5178/verify-email",
        email_verification_resend_cooldown_seconds=1,
        smtp_host="127.0.0.1",
        smtp_port=1026,
        smtp_from_email="local@example.com",
        smtp_starttls=False,
        auth_rate_limit_requests=10000,
        password_reset_rate_limit_requests=10000,
        _env_file=None,
    )
    with socketserver.ThreadingTCPServer(("127.0.0.1", 1026), MailCapture) as smtp:
        threading.Thread(target=smtp.serve_forever, daemon=True).start()
        try:
            uvicorn.run(create_app(settings), host="127.0.0.1", port=8005)
        finally:
            smtp.shutdown()


if __name__ == "__main__":
    main()
