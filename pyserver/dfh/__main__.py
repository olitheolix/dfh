import sys

import uvicorn

import dfh.logstreams

if __name__ == "__main__":  # codecov-skip
    try:
        dfh.logstreams.setup("info")
        uvicorn.run("dfh.api:app", port=5001, log_level="info")
    except KeyboardInterrupt:
        print("User abort")
        sys.exit(1)
