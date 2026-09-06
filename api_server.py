"""Reseller HTTP API — screenshots mein 'Dear API user...' messages aur
'Api Key' button isi feature ka hissa hain.

Endpoints (header: X-API-Key: <user api key>):
  GET  /api/me        -> balance, user info
  GET  /api/products  -> products with live price & stock
  POST /api/buy       -> {"product_id": N} -> buys 1 item, deducts balance

Run: thread mein `python -m http.server` style nahi — aiohttp use hota hai.
"""
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from db import price_of

log = logging.getLogger(__name__)


def make_handler(db):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _auth(self):
            key = self.headers.get("X-API-Key", "")
            if not key:
                return None
            return db.get_user_by_apikey(key)

        def log_message(self, *a):
            pass

        def do_GET(self):
            u = self._auth()
            if not u:
                return self._send(401, {"ok": False, "error": "invalid api key"})
            if self.path == "/api/me":
                return self._send(200, {"ok": True, "user_id": u["user_id"],
                                        "username": u["username"],
                                        "balance": u["balance"]})
            if self.path == "/api/products":
                items = []
                for p in db.list_products(0, 500, active_only=True):
                    price, on_sale = price_of(p)
                    items.append({"id": p["id"], "name": p["name"], "price": price,
                                  "on_sale": on_sale, "stock": p["stock_count"]})
                return self._send(200, {"ok": True, "products": items})
            return self._send(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            u = self._auth()
            if not u:
                return self._send(401, {"ok": False, "error": "invalid api key"})
            if self.path == "/api/buy":
                try:
                    ln = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(ln) or b"{}")
                    pid = int(body.get("product_id"))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad request"})
                res = db.purchase(u["user_id"], pid)
                if not res["ok"]:
                    return self._send(400, {"ok": False, "error": res["err"]})
                return self._send(200, {"ok": True, "order_id": res["order_id"],
                                        "product": res["product"],
                                        "price_paid": res["price"],
                                        "item": res["content"]})
            return self._send(404, {"ok": False, "error": "not found"})
    return H


def start_api_server(db, port):
    handler = make_handler(db)
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)

    def run():
        log.info("Reseller API listening on port %s", port)
        server.serve_forever()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return server
