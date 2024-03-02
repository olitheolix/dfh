import sys

import uvicorn

import dfh.logstreams
import dfh.api

if __name__ == "__main__":  # codecov-skip
    cfg, err = dfh.api.compile_server_config()
    assert not err
    try:
        dfh.logstreams.setup(cfg.loglevel)
        uvicorn.run("dfh.api:app", host=cfg.host, port=cfg.port, log_level=cfg.loglevel)
    except KeyboardInterrupt:
        print("User abort")
        sys.exit(1)
