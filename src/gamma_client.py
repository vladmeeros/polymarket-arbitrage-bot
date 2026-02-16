import requests
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

class GammaClient:
    BASE_URL = "https://gamma-api.polymarket.com"

    COIN_NAMES = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "XRP": "xrp",
    }

    MONTHS = ["january", "february", "march", "april", "may", "june",
              "july", "august", "september", "october", "november", "december"]

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()

    def _get_et_time(self) -> datetime:
        utc_now = datetime.now(timezone.utc)
        et_offset = timedelta(hours=-5)
        return utc_now + et_offset

    def _build_hourly_slug(self, coin: str, dt: datetime) -> str:
        coin_name = self.COIN_NAMES.get(coin.upper(), coin.lower())
        month = self.MONTHS[dt.month - 1]
        day = dt.day
        hour = dt.hour % 12
        if hour == 0:
            hour = 12
        ampm = "am" if dt.hour < 12 else "pm"
        return f"{coin_name}-up-or-down-{month}-{day}-{hour}{ampm}-et"

    def get_current_15m_market(self, coin: str) -> Optional[Dict[str, Any]]:
        if coin.upper() not in self.COIN_NAMES:
            raise ValueError(f"Unsupported coin: {coin}")

        et_now = self._get_et_time()
        current_hour = et_now.replace(minute=0, second=0, microsecond=0)
        slug = self._build_hourly_slug(coin, current_hour)

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/events",
                params={"slug": slug},
                timeout=self.timeout
            )
            data = resp.json()
            if data and len(data) > 0:
                return self._parse_market(data[0])
        except Exception as e:
            print(f"Error fetching market: {e}")
        return None

    def get_next_15m_market(self, coin: str) -> Optional[Dict[str, Any]]:
        if coin.upper() not in self.COIN_NAMES:
            raise ValueError(f"Unsupported coin: {coin}")

        et_now = self._get_et_time()
        next_hour = et_now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        slug = self._build_hourly_slug(coin, next_hour)

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/events",
                params={"slug": slug},
                timeout=self.timeout
            )
            data = resp.json()
            if data and len(data) > 0:
                return self._parse_market(data[0])
        except Exception:
            pass
        return None

    def _parse_market(self, event: Dict[str, Any]) -> Dict[str, Any]:
        markets = event.get("markets", [])
        up_token = None
        down_token = None

        if markets:
            m = markets[0]
            outcomes_raw = m.get("outcomes", "[]")
            token_ids_raw = m.get("clobTokenIds", "[]")

            import json
            outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
            token_ids = json.loads(token_ids_raw) if isinstance(token_ids_raw, str) else token_ids_raw

            for i, outcome in enumerate(outcomes):
                if outcome.lower() == "up" and i < len(token_ids):
                    up_token = token_ids[i]
                elif outcome.lower() == "down" and i < len(token_ids):
                    down_token = token_ids[i]

        end_time = event.get("endDate", "")

        return {
            "condition_id": event.get("conditionId", ""),
            "question": event.get("title", ""),
            "slug": event.get("slug", ""),
            "up_token_id": up_token,
            "down_token_id": down_token,
            "end_time": end_time,
        }

    def get_active_market(self, coin: str) -> Optional[Dict[str, Any]]:
        market = self.get_current_15m_market(coin)
        if market and market.get("up_token_id") and market.get("down_token_id"):
            return market
        return self.get_next_15m_market(coin)

    def get_market_info(self, coin: str) -> Optional[Dict[str, Any]]:
        """Returns market info in the format expected by MarketManager."""
        market = self.get_active_market(coin)
        if not market:
            return None

        up_token = market.get("up_token_id")
        down_token = market.get("down_token_id")

        if not up_token or not down_token:
            return None

        return {
            "slug": market.get("slug", ""),
            "question": market.get("question", ""),
            "end_date": market.get("end_time", ""),
            "token_ids": {
                "up": up_token,
                "down": down_token,
            },
            "prices": {
                "up": 0.5,
                "down": 0.5,
            },
            "accepting_orders": True,
        }
