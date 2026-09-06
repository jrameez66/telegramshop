"""@CryptoBot (Crypto Pay API) integration — auto-verified deposits.
Agar CRYPTOBOT_TOKEN set nahi hai to ye module auto-disable rehta hai."""
import logging

import aiohttp

log = logging.getLogger(__name__)

BASE = "https://pay.crypt.bot/api"


class CryptoPay:
    def __init__(self, token):
        self.token = token

    @property
    def enabled(self):
        return bool(self.token)

    async def _call(self, method, **payload):
        try:
            async with aiohttp.ClientSession(
                    headers={"Crypto-Pay-API-Token": self.token}) as s:
                async with s.post(f"{BASE}/{method}", json=payload,
                                  timeout=aiohttp.ClientTimeout(total=20)) as r:
                    data = await r.json()
                    if not data.get("ok"):
                        log.warning("CryptoPay %s failed: %s", method, data)
                        return None
                    return data["result"]
        except Exception as e:
            log.error("CryptoPay error: %s", e)
            return None

    async def create_invoice(self, amount_usd, payload=""):
        return await self._call(
            "createInvoice", asset="USDT", amount=str(amount_usd),
            description="Wallet Top-up", payload=str(payload),
            expires_in=1800, allow_comments=False, allow_anonymous=False)

    async def get_invoice(self, invoice_id):
        res = await self._call("getInvoices", invoice_ids=str(invoice_id))
        if res and res.get("items"):
            return res["items"][0]
        return None

    async def is_paid(self, invoice_id):
        inv = await self.get_invoice(invoice_id)
        return bool(inv and inv.get("status") == "paid")
