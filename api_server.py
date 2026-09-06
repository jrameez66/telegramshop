"""Reseller HTTP API v2 — screenshots ke 'Reseller Product API' panel ka backend.

Auth (teeno tareeqe support):
  Authorization: Bearer YOUR_KEY
  x-api-key: YOUR_KEY
  ?api_key=YOUR_KEY

Endpoints:
  GET  /api/products  -> products with live price & stock
  GET  /api/balance   -> wallet balance
  GET  /api/me        -> balance + info
  POST /api/order     -> {"product_id": 123, "quantity": 1, "request_id": "my-order-001"}
"""
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

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
            key = ""
            auth = self.headers.get("Authorization", "")
            if auth.lower().startswith("bearer "):
                key = auth[7:].strip()
            if not key:
                key = self.headers.get("x-api-key", "").strip()
            if not key:
                key = parse_qs(urlparse(self.path).query).get("api_key", [""])[0]
            if not key:
                return None
            return db.get_user_by_apikey(key)

        def _path(self):
            return urlparse(self.path).path.rstrip("/")

        def log_message(self, *a):
            pass

        def do_GET(self):
            u = self._auth()
            if not u:
                return self._send(401, {"ok": False, "error": "invalid or disabled api key"})
            path = self._path()
            if path in ("/api/me", "/api/balance"):
                return self._send(200, {"ok": True, "user_id": u["user_id"],
                                        "username": u["username"],
                                        "balance": u["balance"]})
            if path == "/api/products":
                items = []
                for p in db.list_products(0, 500, active_only=True):
                    price, on_sale = price_of(p)
                    items.append({"id": p["id"], "name": p["name"], "price": price,
                                  "base_price": p["price"], "on_sale": on_sale,
                                  "stock": p["stock_count"],
                                  "warranty": p.get("warranty", "")})
                return self._send(200, {"ok": True, "products": items})
            return self._send(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            u = self._auth()
            if not u:
                return self._send(401, {"ok": False, "error": "invalid or disabled api key"})
            if self._path() in ("/api/order", "/api/buy"):
                try:
                    ln = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(ln) or b"{}")
                    pid = int(body.get("product_id"))
                    qty = max(1, int(body.get("quantity", 1)))
                    rid = str(body.get("request_id", ""))[:64]
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad request"})
                # idempotency — same request_id dobara charge nahi hota
                if rid:
                    cached = db.get_api_request(u["user_id"], rid)
                    if cached:
                        return self._send(200, json.loads(cached))
                res = db.purchase_multi(u["user_id"], pid, qty, source="api")
                if not res["ok"]:
                    out = {"ok": False, "error": res["err"]}
                    if res["err"] == "stock":
                        out["available"] = res.get("available", 0)
                    if res["err"] == "balance":
                        out["need"] = res.get("need")
                    return self._send(400, out)
                out = {"ok": True, "order_id": res["order_id"], "product": res["product"],
                       "quantity": res["qty"], "price_paid": res["total"],
                       "items": res["items"],
                       "balance_left": db.get_user(u["user_id"])["balance"]}
                if rid:
                    db.save_api_request(u["user_id"], rid, json.dumps(out))
                return self._send(200, out)
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
