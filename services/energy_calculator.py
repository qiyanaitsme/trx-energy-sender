from config import config


class EnergyCalculator:
    @staticmethod
    def calculate_price(energy_amount: int, price_per_unit: float | None = None) -> float:
        if price_per_unit is None:
            price_per_unit = config.ENERGY_PRICE_TRX
        return energy_amount * price_per_unit

    @staticmethod
    def calculate_commission(has_usdt: bool, with_discount: bool = True) -> int:
        if with_discount:
            return config.COMMISSION_DISCOUNTED if has_usdt else config.COMMISSION_DISCOUNTED_HIGH
        return config.COMMISSION_WITH_USDT if has_usdt else config.COMMISSION_WITHOUT_USDT

    @staticmethod
    def sun_to_trx(sun: int) -> float:
        return sun / 1_000_000

    @staticmethod
    def trx_to_sun(trx: float) -> int:
        return int(trx * 1_000_000)
