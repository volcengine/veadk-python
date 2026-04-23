from pathlib import Path
import yaml

from sdk.core_engine import IntentVanna, SQLVanna

_brain = None
_hands = None
_config_path = None


def init_engine(config_path: str | None = None):
    global _brain, _hands, _config_path
    _config_path = config_path
    _brain = None
    _hands = None


def _load_config() -> dict:
    if _config_path:
        path = Path(_config_path)
    else:
        path = Path(__file__).resolve().parents[2] / "config.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_brain() -> IntentVanna:
    global _brain
    if _brain is None:
        cfg = _load_config()
        _brain = IntentVanna(cfg["intent_engine"])
    return _brain


def get_hands() -> SQLVanna:
    global _hands
    if _hands is None:
        cfg = _load_config()
        _hands = SQLVanna(cfg["sql_engine"])
    return _hands
