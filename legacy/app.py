"""Legacy entry point — delegates to create_app()."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    cfg = app.config["CONFIG_CLASS"]
    app.run(
        host=getattr(cfg, "HOST", "127.0.0.1"),
        port=int(getattr(cfg, "PORT", 5001)),
        debug=getattr(cfg, "DEBUG", False),
    )
