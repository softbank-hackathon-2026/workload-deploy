# Smallest Python web app for the on-prem playbook check (validate.yml). Reads PORT like a real deployed app.
import http.server
import os


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        ok = self.path in ("/", "/health")
        self.send_response(200 if ok else 404)
        self.end_headers()
        self.wfile.write(b'{"status": "ok", "runtime": "python"}' if ok else b"{}")


http.server.HTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()
