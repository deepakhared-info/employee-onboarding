import asyncio

from src.app import app
from uvicorn import run


def selector_loop_factory():
    return asyncio.SelectorEventLoop()


if __name__ == "__main__":
    run("main:app", port=8080, loop="main:selector_loop_factory", reload=True)
