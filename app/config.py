import os
import json
from pathlib import Path
from typing import Any, Dict

# Locate project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

def find_config_file() -> Path:
    env_cfg = os.environ.get("CONFIG_PATH")
    if env_cfg and Path(env_cfg).is_file():
        return Path(env_cfg)
    
    candidate = BASE_DIR / "config.json"
    if candidate.is_file():
        return candidate
    
    candidate_cwd = Path.cwd() / "config.json"
    if candidate_cwd.is_file():
        return candidate_cwd
        
    return candidate

def read_config_json() -> Dict[str, Any]:
    cfg_path = find_config_file()
    if cfg_path.is_file():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

class Settings:
    """
    Application configuration with multi-source hierarchy:
    Environment Variables > config.json > Default values.
    Properties dynamically resolve to ensure test overrides take immediate effect.
    """
    
    @property
    def pin(self) -> str:
        # 1. APP_PIN env var
        env_pin = os.environ.get("APP_PIN")
        if env_pin is not None and env_pin.strip() != "":
            return env_pin.strip()
        
        # 2. config.json
        cfg = read_config_json()
        cfg_pin = cfg.get("pin") or cfg.get("app_pin")
        if cfg_pin is not None and str(cfg_pin).strip() != "":
            return str(cfg_pin).strip()
            
        # 3. Default
        return "7777"

    @property
    def port(self) -> int:
        env_port = os.environ.get("PORT")
        if env_port is not None and env_port.strip() != "":
            try:
                return int(env_port.strip())
            except ValueError:
                pass
        cfg = read_config_json()
        if "port" in cfg:
            try:
                return int(cfg["port"])
            except ValueError:
                pass
        return 8000

    @property
    def host(self) -> str:
        env_host = os.environ.get("HOST")
        if env_host is not None and env_host.strip() != "":
            return env_host.strip()
        cfg = read_config_json()
        if "host" in cfg and cfg["host"]:
            return str(cfg["host"]).strip()
        return "0.0.0.0"

    @property
    def default_group_id(self) -> int:
        env_gid = os.environ.get("DEFAULT_GROUP_ID")
        if env_gid is not None and env_gid.strip() != "":
            try:
                return int(env_gid.strip())
            except ValueError:
                pass
        cfg = read_config_json()
        if "default_group_id" in cfg:
            try:
                return int(cfg["default_group_id"])
            except ValueError:
                pass
        return 1458

    @property
    def rank_cache_ttl(self) -> float:
        env_ttl = os.environ.get("RANK_CACHE_TTL")
        if env_ttl:
            try:
                return float(env_ttl)
            except ValueError:
                pass
        cfg = read_config_json()
        if "refresh_interval_sec" in cfg:
            try:
                return float(cfg["refresh_interval_sec"])
            except ValueError:
                pass
        return 15.0

    @property
    def group_cache_ttl(self) -> float:
        env_ttl = os.environ.get("GROUP_CACHE_TTL")
        if env_ttl:
            try:
                return float(env_ttl)
            except ValueError:
                pass
        return 300.0

    @property
    def token_expire_seconds(self) -> int:
        env_exp = os.environ.get("TOKEN_EXPIRE_SECONDS")
        if env_exp:
            try:
                return int(env_exp)
            except ValueError:
                pass
        return 2592000  # 30 days

    @property
    def hero_nickname(self) -> str:
        env_nick = os.environ.get("HERO_NICKNAME")
        if env_nick is not None:
            return env_nick.strip()
        cfg = read_config_json()
        return str(cfg.get("hero_nickname", "")).strip()

    @property
    def default_stake(self) -> str:
        env_stake = os.environ.get("DEFAULT_STAKE")
        if env_stake is not None and env_stake.strip() != "":
            return env_stake.strip()
        cfg = read_config_json()
        return str(cfg.get("stake", "$0.25")).strip()

    @property
    def static_dir(self) -> Path:
        return BASE_DIR / "static"

settings = Settings()

def get_settings() -> Settings:
    return settings
