import argparse

from app.web import run_server


parser = argparse.ArgumentParser(description="Run the Luculent web application")
parser.add_argument(
    "--open-browser",
    action="store_true",
    help="open Luculent in the default browser after startup",
)
parser.add_argument("--host", default="127.0.0.1", help=argparse.SUPPRESS)
parser.add_argument("--port", type=int, default=0, help=argparse.SUPPRESS)
arguments = parser.parse_args()
run_server(
    open_browser=arguments.open_browser,
    host=arguments.host,
    port=arguments.port,
)
