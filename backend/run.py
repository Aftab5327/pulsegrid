"""Start the backend.

Use this rather than `uvicorn app.main:app` directly. On Windows the default
event loop is the proactor loop, which has no add_reader/add_writer, and
aiomqtt's transport needs them. The policy has to be set before uvicorn builds
its loop — importing app.main is too late, because uvicorn imports the app
from inside the already-running loop.

    python run.py
    python run.py --port 9000
"""

import argparse
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn  # noqa: E402  (must follow the policy call above)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the DigiSpace telemetry backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        loop="asyncio",
    )
