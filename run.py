#!/usr/bin/env python3
"""Run the Smart Environment Monitor Flask dashboard (Assignment 2)."""

from api import create_app

app = create_app()

if __name__ == "__main__":
    cfg = app.config["CONFIG_CLASS"]
    app.run(
        host=getattr(cfg, "HOST", "127.0.0.1"),
        port=int(getattr(cfg, "PORT", 5001)),
        debug=getattr(cfg, "DEBUG", False),
    )
