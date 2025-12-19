import asyncio
import logging
from typing import Any
from functools import wraps

from tronpy import Tron
from tronpy.keys import PrivateKey
from tronpy.providers import HTTPProvider

from config import config
from utils.formatting import mask_address

logger = logging.getLogger(__name__)

NETWORKS = {
    "mainnet": {
        "provider": "https://api.trongrid.io",
        "usdt_contract": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    },
    "nile": {
        "provider": "https://nile.trongrid.io",
        "usdt_contract": "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj",
    },
}

MAX_RETRIES = 3
RETRY_DELAY = 2


def with_retry(max_retries: int = MAX_RETRIES, delay: float = RETRY_DELAY):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (2 ** attempt)
                        logger.warning(f"{func.__name__} attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"{func.__name__} failed after {max_retries} attempts: {e}")
            return {"success": False, "error": str(last_error)}
        return wrapper
    return decorator


class TronService:
    def __init__(
        self,
        private_key: str | None = None,
        wallet_address: str | None = None,
        api_key: str | None = None,
    ):
        self.private_key = private_key or config.TRON_PRIVATE_KEY
        self.wallet_address = wallet_address or config.TRON_WALLET_ADDRESS
        api_key = api_key or config.TRONGRID_API_KEY

        network = config.TRON_NETWORK.lower()
        network_config = NETWORKS.get(network, NETWORKS["mainnet"])

        provider = HTTPProvider(network_config["provider"], api_key=api_key)
        self.client = Tron(provider=provider)
        self.usdt_contract = network_config["usdt_contract"]
        self.network = network

        logger.info(f"TronService initialized for network: {network}")

    def _get_priv_key(self) -> PrivateKey:
        return PrivateKey(bytes.fromhex(self.private_key))

    @with_retry()
    async def get_energy_balance(self, address: str) -> dict[str, Any]:
        try:
            account = self.client.get_account_resource(address)
            balance_info = self.client.get_account_balance(address)
            return {
                "energy": account.get("EnergyUsed", 0),
                "energy_limit": account.get("EnergyLimit", 0),
                "energy_available": account.get("EnergyLimit", 0) - account.get("EnergyUsed", 0),
                "free_net_limit": account.get("freeNetLimit", 0),
                "balance": int(balance_info * 1_000_000),
            }
        except Exception as e:
            logger.error(f"Error getting energy balance: {e}")
            return {"error": str(e)}

    async def get_bot_available_energy(self) -> int:
        balance = await self.get_energy_balance(self.wallet_address)
        if "error" in balance:
            return 0
        return balance.get("energy_available", 0)

    async def has_enough_energy(self, required_energy: int) -> tuple[bool, int]:
        available = await self.get_bot_available_energy()
        return available >= required_energy, available

    @with_retry()
    async def calculate_energy_for_transfer(self, recipient_address: str) -> dict[str, Any]:
        try:
            has_usdt = False
            try:
                contract = self.client.get_contract(self.usdt_contract)
                balance = contract.functions.balanceOf(recipient_address)
                has_usdt = balance > 0
            except Exception:
                has_usdt = False

            if has_usdt:
                base_energy = 65_000
            else:
                base_energy = 131_000

            required_energy = int(base_energy * 1.1)
            return {
                "required_energy": required_energy,
                "base_energy": base_energy,
                "has_usdt": has_usdt,
            }
        except Exception as e:
            logger.error(f"Error calculating energy: {e}")
            return {"error": str(e)}

    def _energy_to_sun(self, energy_amount: int) -> int:
        trx_needed = max(1, energy_amount // 70)
        return trx_needed * 1_000_000

    @with_retry()
    async def delegate_energy(self, to_address: str, energy_amount: int) -> dict[str, Any]:
        try:
            has_enough, available = await self.has_enough_energy(energy_amount)
            if not has_enough:
                logger.error(f"Not enough energy: need {energy_amount}, have {available}")
                return {
                    "success": False,
                    "error": f"Недостаточно энергии у бота. Нужно: {energy_amount:,}, доступно: {available:,}",
                }

            priv_key = self._get_priv_key()
            balance_sun = self._energy_to_sun(energy_amount)
            logger.info(f"Delegating {energy_amount} energy to {mask_address(to_address)}")

            txn = (
                self.client.trx.delegate_resource(
                    owner=self.wallet_address,
                    receiver=to_address,
                    balance=balance_sun,
                    resource="ENERGY",
                    lock=False,
                )
                .build()
                .sign(priv_key)
            )
            result = txn.broadcast()

            if result.get("result"):
                tx_hash = result.get("txid", "")
                logger.info(f"Energy delegated successfully: {tx_hash}")
                return {
                    "success": True,
                    "transaction_hash": tx_hash,
                    "energy_amount": energy_amount,
                    "trx_delegated": balance_sun // 1_000_000,
                }
            error_msg = result.get("message", "Transaction failed")
            logger.error(f"Delegation failed: {error_msg}")
            return {"success": False, "error": error_msg}
        except Exception as e:
            logger.error(f"Error delegating energy: {e}")
            return {"success": False, "error": str(e)}

    @with_retry()
    async def undelegate_energy(self, from_address: str, energy_amount: int) -> dict[str, Any]:
        try:
            priv_key = self._get_priv_key()
            balance_sun = self._energy_to_sun(energy_amount)

            logger.info(f"Undelegating {energy_amount} energy from {mask_address(from_address)}")

            txn = (
                self.client.trx.undelegate_resource(
                    owner=self.wallet_address,
                    receiver=from_address,
                    balance=balance_sun,
                    resource="ENERGY",
                )
                .build()
                .sign(priv_key)
            )
            result = txn.broadcast()

            if result.get("result"):
                tx_hash = result.get("txid", "")
                logger.info(f"Energy undelegated successfully: {tx_hash}")
                return {"success": True, "transaction_hash": tx_hash}
            error_msg = result.get("message", "Transaction failed")
            logger.error(f"Undelegation failed: {error_msg}")
            return {"success": False, "error": error_msg}
        except Exception as e:
            logger.error(f"Error undelegating energy: {e}")
            return {"success": False, "error": str(e)}

    async def freeze_trx_for_energy(self, amount_sun: int) -> dict[str, Any]:
        try:
            priv_key = self._get_priv_key()
            txn = (
                self.client.trx.freeze_balance_v2(
                    owner=self.wallet_address,
                    amount=amount_sun,
                    resource="ENERGY",
                )
                .build()
                .sign(priv_key)
            )
            result = txn.broadcast()

            if result.get("result"):
                return {
                    "success": True,
                    "transaction_hash": result.get("txid", ""),
                    "frozen_amount": amount_sun,
                }
            return {"success": False, "error": "Transaction failed"}
        except Exception as e:
            logger.error(f"Error freezing TRX: {e}")
            return {"success": False, "error": str(e)}

    def validate_address(self, address: str) -> bool:
        if not address or not address.startswith("T") or len(address) != 34:
            return False
        try:
            return self.client.is_address(address)
        except Exception:
            return False

    async def check_incoming_trx(
        self,
        expected_amount_trx: float,
        since_timestamp: int,
        tolerance: float = 0.01,
    ) -> dict[str, Any]:
        import aiohttp

        try:
            base_url = NETWORKS.get(self.network, NETWORKS["mainnet"])["provider"]
            url = f"{base_url}/v1/accounts/{self.wallet_address}/transactions"
            params = {
                "only_to": "true",
                "only_confirmed": "true",
                "limit": 20,
                "min_timestamp": since_timestamp,
            }
            headers = {}
            if config.TRONGRID_API_KEY:
                headers["TRON-PRO-API-KEY"] = config.TRONGRID_API_KEY

            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params, headers=headers) as resp:
                    if resp.status != 200:
                        logger.error(f"TronGrid API error: {resp.status}")
                        return {"found": False, "error": f"API error: {resp.status}"}
                    data = await resp.json()

            expected_sun = int(expected_amount_trx * 1_000_000)
            tolerance_sun = int(tolerance * 1_000_000)

            for tx in data.get("data", []):
                if tx.get("raw_data", {}).get("contract", [{}])[0].get("type") == "TransferContract":
                    contract_data = tx["raw_data"]["contract"][0]["parameter"]["value"]
                    amount = contract_data.get("amount", 0)
                    if abs(amount - expected_sun) <= tolerance_sun:
                        from_address = self.client.to_base58check_address(
                            contract_data.get("owner_address", "")
                        )
                        return {
                            "found": True,
                            "transaction_hash": tx.get("txID", ""),
                            "amount": amount / 1_000_000,
                            "from_address": from_address,
                        }
            return {"found": False}
        except Exception as e:
            logger.error(f"Error checking incoming TRX: {e}")
            return {"found": False, "error": str(e)}
