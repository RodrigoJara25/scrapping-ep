"""Arranca la API local.  Uso:  python run.py  [--host H] [--port P] [--reload]"""

import argparse

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser(description="Bot Normas Legales - El Peruano")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true", help="autorecarga en desarrollo")
    args = ap.parse_args()

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
