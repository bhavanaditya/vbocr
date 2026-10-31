"""Loading of settings.yaml and suppliers.yaml."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_DIR = Path(os.environ.get("VBOCR_CONFIG_DIR", ROOT_DIR / "config"))


LOCAL_SETTINGS = "settings.local.yaml"


class Settings:
    def __init__(self, config_dir: Optional[Path] = None):
        config_dir = Path(config_dir or DEFAULT_CONFIG_DIR)
        self.config_dir = config_dir
        self.data: Dict[str, Any] = _load_yaml(config_dir / "settings.yaml")
        # Per-PC settings (access key, oneDNN switch, ...). Not in git, so updates never
        # overwrite them and `git pull` never conflicts with them.
        local = config_dir / LOCAL_SETTINGS
        if local.exists():
            _deep_merge(self.data, _load_yaml(local))
        self.suppliers: List[Dict[str, Any]] = (
            _load_yaml(config_dir / "suppliers.yaml").get("suppliers") or []
        )

    @property
    def local_settings_path(self) -> Path:
        return self.config_dir / LOCAL_SETTINGS

    @property
    def checks(self) -> Dict[str, Any]:
        return self.data.get("checks") or {}

    @property
    def history(self) -> Dict[str, Any]:
        return self.data.get("history") or {}

    @property
    def pdf(self) -> Dict[str, Any]:
        return self.data.get("pdf") or {}

    @property
    def item_master(self) -> Dict[str, Any]:
        return self.data.get("item_master") or {}

    def resolve(self, path: str) -> Path:
        """A path from the settings: absolute, or relative to the install folder."""
        p = Path(path)
        return p if p.is_absolute() else ROOT_DIR / p

    @property
    def server(self) -> Dict[str, Any]:
        return self.data.get("server") or {}

    @property
    def ocr(self) -> Dict[str, Any]:
        return self.data.get("ocr") or {}

    @property
    def output(self) -> Dict[str, Any]:
        return self.data.get("output") or {}

    def match_supplier(self, text: str) -> Optional[Dict[str, Any]]:
        lowered = text.lower()
        for supplier in self.suppliers:
            if any(str(key).lower() in lowered for key in supplier.get("match") or []):
                return supplier
        return None

    def header_labels(self, supplier: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
        return _merge_lists(self.data.get("header_fields") or {}, (supplier or {}).get("header_fields"))

    def item_columns(self, supplier: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
        return _merge_lists(self.data.get("item_columns") or {}, (supplier or {}).get("item_columns"))

    def description_patterns(self, supplier: Optional[Dict[str, Any]]) -> List[str]:
        return list((supplier or {}).get("description_patterns") or []) + list(
            self.data.get("description_patterns") or []
        )

    @property
    def colour_codes(self) -> Dict[str, str]:
        return {str(k).upper(): str(v) for k, v in (self.data.get("colour_codes") or {}).items()}


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError("Config file not found: {}".format(path))
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _deep_merge(base: Dict[str, Any], extra: Dict[str, Any]) -> None:
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _merge_lists(base: Dict[str, List[str]], extra: Optional[Dict[str, List[str]]]) -> Dict[str, List[str]]:
    merged = {k: list(v or []) for k, v in base.items()}
    for key, values in (extra or {}).items():
        merged[key] = list(values or []) + merged.get(key, [])
    return merged
