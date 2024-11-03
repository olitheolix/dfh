import asyncio
import os
import sys

import square
from hypercorn.asyncio import serve
from hypercorn.config import Config

import dfh.api
import dfh.logstreams
import dfh.routers.uam

if __name__ == "__main__":  # codecov-skip
    square.square.setup_logging(2)
    cfg, err = dfh.api.compile_server_config()
    assert not err
    dfh.routers.uam.UAM_DB.root.owner = os.environ.get("DFH_ROOT", "")

    try:
        dfh.logstreams.setup(cfg.loglevel)
        hypercorn_cfg = Config()
        hypercorn_cfg.bind = [f"{cfg.host}:{cfg.port}"]
        asyncio.run(serve(dfh.api.make_app(), hypercorn_cfg))  # type: ignore
    except KeyboardInterrupt:
        print("User abort")
        sys.exit(1)
