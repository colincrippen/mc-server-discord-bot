import asyncio
import os
import signal
import typing
from typing import Literal, Optional

import aiofiles

if typing.TYPE_CHECKING:
    from asyncio.subprocess import Process

type ServerState = Literal["off", "starting", "running", "stopping"]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "../test_server_dir/server"))
PID_FILE = os.path.join(SERVER_DIR, "server.pid")

JAVA_COMMAND = [
    "java",
    "-Xmx6G",
    "-Xms6G",
    "-Dlog4j2.formatMsgNoLookups=true",
    "-jar",
    "fabric-server-launcher.jar",
    "-nogui",
]


class MCServer:
    def __init__(self) -> None:
        self.process: Optional[Process] = None
        self.state: ServerState = "off"
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        if os.path.exists(PID_FILE):
            print("server already running")
            return

        self.process = await asyncio.create_subprocess_exec(
            *JAVA_COMMAND,
            cwd=SERVER_DIR,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        self.state = "starting"

        async with aiofiles.open(PID_FILE, "w") as f:
            await f.write(str(self.process.pid))

        print(f"Server started with PID {self.process.pid}.")

        asyncio.create_task(self._read_output())  # noqa: RUF006

    async def _read_output(self) -> None:
        while self.state != "off":
            line_bytes = await self.process.stdout.readline()  # type: ignore
            if line_bytes:
                line_str = line_bytes.decode().strip()
                print(line_str)

                if "Loading Xaero's World Map - Stage 2/2 (Server)" in line_str:
                    self.state = "running"
                    await self.send_command("say Server is online!")

                if self.state == "stopping" and "Stopped IO worker!" in line_str:
                    print("Detected shutdown complete message.")
                    self._shutdown_event.set()

    async def send_command(self, command: str):
        if self.process and self.process.stdin:
            print(f"Sending command: {command}")
            self.process.stdin.write((command + "\n").encode())
            await self.process.stdin.drain()

    async def stop(self, time: int = 15):
        if not self.process:
            print("No server running.")
            return

        if self.state == "starting":
            print("cannot stop until fully started")
            return
        elif self.state == "stopping":
            print("already trying to stop!")
            return

        self.state = "stopping"

        await self.send_command("stop")
        print("Sent 'stop'. Waiting for graceful shutdown...")

        try:
            await asyncio.wait_for(self._shutdown_event.wait(), timeout=time)
        except asyncio.TimeoutError:
            print("Shutdown timeout. Sending SIGINT.")

        try:
            os.killpg(self.process.pid, signal.SIGINT)
        except ProcessLookupError:
            print("Process already exited.")
        except Exception as e:
            print("SIGINT error:", e)

        self.state = "off"

        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)


# async def main():
#     server = MCServer()

#     await server.start()
#     await asyncio.sleep(45)
#     await server.stop()


# if __name__ == "__main__":
#     asyncio.run(main())
