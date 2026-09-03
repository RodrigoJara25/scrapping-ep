"""Arranca la API.  Uso:  python run.py  [--host H] [--port P] [--reload]

En hosts tipo Render/Railway se respeta la variable de entorno PORT.
"""

import argparse
import os

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser(description="Bot Normas Legales - El Peruano")
    ap.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    ap.add_argument("--reload", action="store_true", help="autorecarga en desarrollo")
    args = ap.parse_args()

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
