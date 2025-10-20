import json
import os

from .util import uopen

CONFIG_FILEPATH = 'dumpMeta/config.json'

def update_config(dump_dir: str, config: dict):
    """Only updates given keys in config."""
    _config = get_config(dump_dir)
    config = {**_config, **config}
    print("Config updated:", config)

    os.makedirs(os.path.join(dump_dir, 'dumpMeta'), exist_ok=True)
    with uopen(os.path.join(dump_dir, CONFIG_FILEPATH), 'w') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def get_config(dump_dir: str) -> dict:
    """Load config from dump directory. Return empty dict if not exists."""
    path = os.path.join(dump_dir, CONFIG_FILEPATH)
    if os.path.exists(path):
        with uopen(path, 'r') as f:
            return json.load(f)
    return {}