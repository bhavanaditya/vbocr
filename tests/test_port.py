"""The server checks its port before loading the OCR engine (about 20 s), so a busy port is
reported at once. No OCR engine needed."""

import http.server
import socket
import threading

from vbocr.server import port_problem


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_free_port_is_fine():
    assert port_problem("127.0.0.1", _free_port()) == ""


def test_port_used_by_another_program():
    other = socket.socket()
    other.bind(("127.0.0.1", 0))
    other.listen()
    try:
        message = port_problem("127.0.0.1", other.getsockname()[1])
    finally:
        other.close()
    assert message.startswith("Port ") and "another program" in message and "server.port" in message


def test_vbocr_already_running():
    class Health(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"status": "ok", "version": "1.2.0"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Health)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        message = port_problem("127.0.0.1", server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
    assert message.startswith("VB OCR is already running")
