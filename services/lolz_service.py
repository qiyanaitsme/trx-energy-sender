import logging
from typing import Any

import aiohttp

from config import config, ENERGY_PACKAGES

logger = logging.getLogger(__name__)

LOLZ_API_BASE = "https://prod-api.lzt.market"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)

# Пакеты загружаются из config.py (который берёт из .env)
ENERGY_PACKAGES_RUB = ENERGY_PACKAGES


class LolzPaymentService:
    def __init__(self, api_token: str | None = None):
        self.api_token = api_token or config.LOLZ_API_TOKEN
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def create_invoice(
        self,
        amount: int,
        payment_id: str,
        comment: str = "Оплата энергии TRX",
        url_success: str = "",
        merchant_id: int = 125,
        lifetime: int = 900,
    ) -> dict[str, Any]:
        url = f"{LOLZ_API_BASE}/invoice"
        payload = {
            "currency": "rub",
            "amount": amount,
            "payment_id": payment_id,
            "comment": comment,
            "merchant_id": merchant_id,
            "lifetime": lifetime,
        }
        if url_success:
            payload["url_success"] = url_success

        try:
            async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    data = await resp.json()
                    invoice = data.get("invoice", {})
                    if not invoice:
                        error_msg = data.get("errors", ["Unknown error"])
                        if isinstance(error_msg, list):
                            error_msg = error_msg[0] if error_msg else "Unknown error"
                        logger.error(f"LOLZ API error: {data}")
                        return {"success": False, "error": error_msg}
                    logger.info(f"Invoice created: {invoice.get('invoice_id')}")
                    return {
                        "success": True,
                        "invoice_id": invoice.get("invoice_id"),
                        "payment_url": invoice.get("url"),
                        "amount": invoice.get("amount"),
                        "status": invoice.get("status"),
                        "expires_at": invoice.get("expires_at"),
                    }
        except Exception as e:
            logger.error(f"Error creating invoice: {e}")
            return {"success": False, "error": str(e)}

    async def check_invoice(
        self,
        invoice_id: int | None = None,
        payment_id: str | None = None,
        expected_amount: float | None = None,
    ) -> dict[str, Any]:
        url = f"{LOLZ_API_BASE}/invoice"
        params = {}
        if invoice_id:
            params["invoice_id"] = invoice_id
        if payment_id:
            params["payment_id"] = payment_id

        try:
            async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
                async with session.get(url, headers=self.headers, params=params) as resp:
                    data = await resp.json()
                    invoice = data.get("invoice", {})
                    if not invoice:
                        error_msg = data.get("errors", ["Invoice not found"])
                        if isinstance(error_msg, list):
                            error_msg = error_msg[0] if error_msg else "Unknown error"
                        return {"success": False, "error": error_msg}

                    status = invoice.get("status", "")
                    is_paid = status == "paid"
                    actual_amount = invoice.get("amount", 0)

                    if is_paid and expected_amount is not None:
                        if abs(actual_amount - expected_amount) > 0.01:
                            logger.error(
                                f"Amount mismatch! Expected: {expected_amount}, Got: {actual_amount}, "
                                f"Invoice: {invoice_id}, Payment: {payment_id}"
                            )
                            return {
                                "success": False,
                                "error": f"Сумма не совпадает: ожидалось {expected_amount}, получено {actual_amount}",
                                "amount_mismatch": True,
                            }

                    return {
                        "success": True,
                        "invoice_id": invoice.get("invoice_id"),
                        "status": status,
                        "is_paid": is_paid,
                        "amount": actual_amount,
                        "paid_date": invoice.get("paid_date"),
                        "payer_user_id": invoice.get("payer_user_id"),
                    }
        except aiohttp.ClientError as e:
            logger.error(f"Network error checking invoice: {e}")
            return {"success": False, "error": f"Ошибка сети: {e}"}
        except Exception as e:
            logger.error(f"Error checking invoice: {e}")
            return {"success": False, "error": str(e)}
