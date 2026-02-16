import os
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass, field, asdict
import yaml


# Environment variable prefix
ENV_PREFIX = "POLY_"


def get_env(name: str, default: str = "") -> str:
    """Get environment variable with prefix."""
    return os.environ.get(f"{ENV_PREFIX}{name}", default)


def get_env_bool(name: str, default: bool = False) -> bool:
    """Get boolean environment variable."""
    val = get_env(name, "").lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


def get_env_int(name: str, default: int = 0) -> int:
    """Get integer environment variable."""
    val = get_env(name, "")
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return default


def get_env_float(name: str, default: float = 0.0) -> float:
    """Get float environment variable."""
    val = get_env(name, "")
    if val:
        try:
            return float(val)
        except ValueError:
            pass
    return default


class ConfigError(Exception):
    pass


class ConfigNotFoundError(ConfigError):
    pass


@dataclass
class BuilderConfig:
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_secret and self.api_passphrase)


@dataclass
class ClobConfig:
    host: str = "https://clob.polymarket.com"
    chain_id: int = 137
    signature_type: int = 2

    def is_valid(self) -> bool:
        return bool(self.host and self.host.startswith("http"))


@dataclass
class RelayerConfig:
    host: str = "https://relayer-v2.polymarket.com"
    tx_type: str = "SAFE"

    def is_configured(self) -> bool:
        return bool(self.host)


@dataclass
class Config:
    safe_address: str = ""
    rpc_url: str = "https://polygon-rpc.com"
    clob: ClobConfig = field(default_factory=ClobConfig)
    relayer: RelayerConfig = field(default_factory=RelayerConfig)
    builder: BuilderConfig = field(default_factory=BuilderConfig)
    default_token_id: str = ""
    default_size: float = 1.0
    default_price: float = 0.5
    data_dir: str = "credentials"
    log_level: str = "INFO"
    use_gasless: bool = False

    def __post_init__(self):
        if self.safe_address:
            self.safe_address = self.safe_address.lower()
        if self.builder.is_configured():
            self.use_gasless = True

    @classmethod
    def load(cls, filepath: str = "config.yaml") -> "Config":
        path = Path(filepath)
        if not path.exists():
            raise ConfigNotFoundError(f"Config file not found: {filepath}")
        with open(path, 'r') as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        config = cls()
        if "safe_address" in data:
            config.safe_address = data["safe_address"]
        if "rpc_url" in data:
            config.rpc_url = data["rpc_url"]
        if "clob" in data:
            clob_data = data["clob"]
            config.clob = ClobConfig(
                host=clob_data.get("host", config.clob.host),
                chain_id=clob_data.get("chain_id", config.clob.chain_id),
                signature_type=clob_data.get("signature_type", config.clob.signature_type),
            )
        if "relayer" in data:
            relayer_data = data["relayer"]
            config.relayer = RelayerConfig(
                host=relayer_data.get("host", config.relayer.host),
                tx_type=relayer_data.get("tx_type", config.relayer.tx_type),
            )
        if "builder" in data:
            builder_data = data["builder"]
            config.builder = BuilderConfig(
                api_key=builder_data.get("api_key", ""),
                api_secret=builder_data.get("api_secret", ""),
                api_passphrase=builder_data.get("api_passphrase", ""),
            )
        if "default_token_id" in data:
            config.default_token_id = data["default_token_id"]
        if "default_size" in data:
            config.default_size = float(data["default_size"])
        if "default_price" in data:
            config.default_price = float(data["default_price"])
        if "data_dir" in data:
            config.data_dir = data["data_dir"]
        if "log_level" in data:
            config.log_level = data["log_level"]
        config.use_gasless = config.builder.is_configured()
        return config

    @classmethod
    def from_env(cls) -> "Config":
        config = cls()
        safe_address = get_env("PROXY_WALLET") or get_env("SAFE_ADDRESS")
        if safe_address:
            config.safe_address = safe_address
        rpc_url = get_env("RPC_URL")
        if rpc_url:
            config.rpc_url = rpc_url
        api_key = get_env("BUILDER_API_KEY")
        api_secret = get_env("BUILDER_API_SECRET")
        api_passphrase = get_env("BUILDER_API_PASSPHRASE")
        if api_key or api_secret or api_passphrase:
            config.builder = BuilderConfig(
                api_key=api_key,
                api_secret=api_secret,
                api_passphrase=api_passphrase,
            )
        clob_host = get_env("CLOB_HOST")
        chain_id = get_env_int("CHAIN_ID", 137)
        if clob_host:
            config.clob = ClobConfig(host=clob_host, chain_id=chain_id)
        elif chain_id != 137:
            config.clob.chain_id = chain_id
        data_dir = get_env("DATA_DIR")
        if data_dir:
            config.data_dir = data_dir
        log_level = get_env("LOG_LEVEL")
        if log_level:
            config.log_level = log_level.upper()
        default_size = get_env_float("DEFAULT_SIZE")
        if default_size:
            config.default_size = default_size
        default_price = get_env_float("DEFAULT_PRICE")
        if default_price:
            config.default_price = default_price
        config.use_gasless = config.builder.is_configured()
        return config

    @classmethod
    def load_with_env(cls, filepath: str = "config.yaml") -> "Config":
        path = Path(filepath)
        if path.exists():
            config = cls.load(filepath)
        else:
            config = cls()
        safe_address = get_env("PROXY_WALLET") or get_env("SAFE_ADDRESS")
        if safe_address:
            config.safe_address = safe_address.lower()
        rpc_url = get_env("RPC_URL")
        if rpc_url:
            config.rpc_url = rpc_url
        api_key = get_env("BUILDER_API_KEY")
        api_secret = get_env("BUILDER_API_SECRET")
        api_passphrase = get_env("BUILDER_API_PASSPHRASE")
        if api_key:
            config.builder.api_key = api_key
        if api_secret:
            config.builder.api_secret = api_secret
        if api_passphrase:
            config.builder.api_passphrase = api_passphrase
        data_dir = get_env("DATA_DIR")
        if data_dir:
            config.data_dir = data_dir
        log_level = get_env("LOG_LEVEL")
        if log_level:
            config.log_level = log_level.upper()
        config.use_gasless = config.builder.is_configured()
        return config

    def save(self, filepath: str = "config.yaml") -> None:
        data = self.to_dict()
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, indent=2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "safe_address": self.safe_address,
            "rpc_url": self.rpc_url,
            "clob": asdict(self.clob),
            "relayer": asdict(self.relayer),
            "builder": asdict(self.builder),
            "default_token_id": self.default_token_id,
            "default_size": self.default_size,
            "default_price": self.default_price,
            "data_dir": self.data_dir,
            "log_level": self.log_level,
        }

    def validate(self) -> List[str]:
        errors = []
        if not self.safe_address:
            errors.append("safe_address is required")
        if not self.rpc_url:
            errors.append("rpc_url is required")
        if not self.clob.is_valid():
            errors.append("clob configuration is invalid")
        if self.use_gasless and not self.builder.is_configured():
            errors.append("gasless mode enabled but builder credentials not configured")
        return errors

    def get_credential_path(self, name: str) -> Path:
        return Path(self.data_dir) / name

    def get_encrypted_key_path(self) -> Path:
        return self.get_credential_path("encrypted_key.json")

    def get_api_creds_path(self) -> Path:
        return self.get_credential_path("api_creds.json")
