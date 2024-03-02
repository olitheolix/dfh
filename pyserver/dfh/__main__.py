import asyncio
import sys

import square
from hypercorn.asyncio import serve
from hypercorn.config import Config

import dfh.api
import dfh.logstreams

if __name__ == "__main__":  # codecov-skip
    square.square.setup_logging(2)
    cfg, err = dfh.api.compile_server_config()
    assert not err
    try:
        dfh.logstreams.setup(cfg.loglevel)
        hypercorn_cfg = Config()
        hypercorn_cfg.bind = [f"{cfg.host}:{cfg.port}"]
        asyncio.run(serve(dfh.api.app, hypercorn_cfg))  # type: ignore
    except KeyboardInterrupt:
        print("User abort")
        sys.exit(1)
