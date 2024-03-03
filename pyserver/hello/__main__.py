import sys

import uvicorn

if __name__ == "__main__":  # codecov-skip
    try:
        uvicorn.run("hello.main:app", host="0.0.0.0", port=6000, log_level="info")
    except KeyboardInterrupt:
        print("User abort")
        sys.exit(1)
