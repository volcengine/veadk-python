import argparse
import json
from pathlib import Path
import yaml

from sdk.core_engine import IntentVanna, SQLVanna


def load_config(config_path: str | None = None) -> dict:
    path = Path(config_path) if config_path else Path(__file__).resolve().parent / "config.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8")
    data = json.loads(content)
    if isinstance(data, list):
        return data
    return []


def _read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8").strip()
    return content or None


def train_brain(config_path: str | None = None, data_dir: str | None = None):
    cfg = load_config(config_path)
    brain = IntentVanna(cfg["intent_engine"])
    base_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent
    glossary_path = base_dir / "glossary.txt"
    samples_path = base_dir / "samples.json"

    glossary = _read_lines(glossary_path) or [
        "术语：'土豪' = user_level >= 5",
        "术语：'流失' = is_active = 0",
        "术语：'MA多头' = close > ma5 > ma10",
    ]
    samples = _read_json(samples_path) or [
        {
            "q": "查一下土豪流失",
            "json": {"intent": "query_metric", "payload": {"filters": ["level>=5"]}},
        },
        {
            "q": "选出MA多头的票",
            "json": {"intent": "screening", "payload": {"factors": ["ma_bull"]}},
        },
        {
            "q": "画个最近营收的图",
            "json": {"intent": "plot_chart", "payload": {"metric": "revenue"}},
        },
    ]

    doc_count = 0
    sample_count = 0
    for term in glossary:
        brain.train(documentation=term)
        doc_count += 1
    for item in samples:
        brain.train(question=item["q"], sql=json.dumps(item["json"], ensure_ascii=False))
        sample_count += 1
    summary = {"pipeline": "brain", "write_count": doc_count + sample_count, "sample_count": sample_count}
    print(json.dumps(summary, ensure_ascii=False))


def train_hands(config_path: str | None = None, data_dir: str | None = None):
    cfg = load_config(config_path)
    hands = SQLVanna(cfg["sql_engine"])
    base_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent
    ddl_path = base_dir / "ddl.sql"
    glossary_path = base_dir / "glossary.txt"
    samples_path = base_dir / "samples.json"

    ddl = _read_text(ddl_path) or "CREATE TABLE user_stats (user_id INT, revenue DOUBLE, dt STRING)"
    definitions = _read_lines(glossary_path) or ["指标：ARPU = revenue / users"]
    samples = _read_json(samples_path) or [
        {"q": "查总营收", "sql": "SELECT sum(revenue) FROM user_stats"},
        {"q": "按天看营收", "sql": "SELECT dt, sum(revenue) FROM user_stats GROUP BY dt"},
    ]

    write_count = 0
    sample_count = 0
    hands.train(ddl=ddl)
    write_count += 1
    for doc in definitions:
        hands.train(documentation=doc)
        write_count += 1
    for item in samples:
        hands.train(question=item["q"], sql=item["sql"])
        sample_count += 1
        write_count += 1
    summary = {"pipeline": "hands", "write_count": write_count, "sample_count": sample_count}
    print(json.dumps(summary, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["brain", "hands", "all"])
    parser.add_argument("--config", default=None)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()

    if args.mode == "brain":
        train_brain(args.config, args.data_dir)
    elif args.mode == "hands":
        train_hands(args.config, args.data_dir)
    else:
        train_brain(args.config, args.data_dir)
        train_hands(args.config, args.data_dir)


if __name__ == "__main__":
    main()
