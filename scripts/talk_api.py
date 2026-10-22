"""可正常退出的API子进程；私有控制文件避免依赖交互控制台信号。"""
from __future__ import annotations
import argparse
import asyncio
from pathlib import Path
import uvicorn


async def serve(args):
    control=Path(args.control_file).resolve()
    if control.exists():
        raise RuntimeError("api_control_marker_exists")
    server=uvicorn.Server(uvicorn.Config(args.app,host=args.host,port=args.port,log_level="info"))
    async def watch():
        while not server.should_exit:
            if control.is_file():
                server.should_exit=True
                return
            await asyncio.sleep(.25)
    watcher=asyncio.create_task(watch())
    try:
        await server.serve()
    finally:
        watcher.cancel()
        await asyncio.gather(watcher,return_exceptions=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host",default="127.0.0.1")
    p.add_argument("--port",type=int,default=8000)
    p.add_argument("--app",default="server.main:app")
    p.add_argument("--control-file",required=True)
    asyncio.run(serve(p.parse_args()))


if __name__=="__main__":main()
