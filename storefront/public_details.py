"""Public address and hours confirmed by the owner; shared with the React footer."""

import json
from pathlib import Path


PUBLIC_DETAILS = json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))
