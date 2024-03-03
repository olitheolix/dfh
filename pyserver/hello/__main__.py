import asyncio
import sys

from hypercorn.asyncio import serve
from hypercorn.config import Config

import dfh.logstreams
import hello.main

if __name__ == "__main__":  # codecov-skip
    try:
        dfh.logstreams.setup("info")
        cfg = Config()
        cfg.bind = ["0.0.0.0:6000"]
        asyncio.run(serve(hello.main.app, cfg))  # type: ignore
    except KeyboardInterrupt:
        print("User abort")
        sys.exit(1)
