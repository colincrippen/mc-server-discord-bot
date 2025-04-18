import asyncio
import os
import re
import signal
import typing
from typing import Literal, Optional

import aiofiles
from dotenv import find_dotenv, load_dotenv

if typing.TYPE_CHECKING:
    from asyncio.subprocess import Process

type ServerState = Literal["off", "starting", "running", "stopping"]

load_dotenv(find_dotenv())
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.getenv("SERVER_DIR", "../../../server")))
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

SHUTDOWN_PATTERN = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] \[Server thread\/INFO\]: Stopped IO worker!$")
LIST_PATTERN = re.compile(r"There (?:are|is) (\d+) of a max of \d+ players online: ?(.*)")


class MCServer:
    def __init__(self) -> None:
        self.process: Optional[Process] = None
        self.state: ServerState = "off"
        self.output_queue: asyncio.Queue[str] = asyncio.Queue()

        self._shutdown_event = asyncio.Event()

    async def _read_output(self) -> None:
        while self.state != "off":
            line_bytes = await self.process.stdout.readline()  # type: ignore
            if line_bytes:
                line_str = line_bytes.decode().strip()

                print(line_str)
                await self.output_queue.put(line_str)

                if SHUTDOWN_PATTERN.match(line_str):
                    if self.state != "stopping":
                        self.state = "stopping"
                        await self._handle_shutdown()
                    else:
                        self._shutdown_event.set()

    async def _handle_shutdown(self) -> str:
        if self.process is None:
            return "No server is running!"

        try:
            await asyncio.sleep(2)  # a bit of delay to add a bit more of a buffer
            os.killpg(self.process.pid, signal.SIGINT)
        except ProcessLookupError:
            print("Process already exited.")
        except Exception as e:
            print("SIGINT error:", e)

        self.state = "off"
        self.process = None
        self._shutdown_event.clear()

        self.output_queue = asyncio.Queue()

        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)

        return "Server has fully shut down!"

    async def start(self) -> str:
        if os.path.exists(PID_FILE):
            return "Server already running!"

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

        while self.state == "starting":
            line = await asyncio.wait_for(self.output_queue.get(), timeout=None)
            if "Loading Xaero's World Map - Stage 2/2 (Server)" in line:
                self.state = "running"

        return "Server is ready!"

    async def stop(self, time: int = 15) -> str:
        match self.state:
            case "off":
                return "No server running."
            case "starting":
                return "Cannot stop until fully started."
            case "stopping":
                return "Already trying to stop!"

        response = await self.get_online_players()
        if "error" in response:
            return f"Error: {response['error']}"

        players = response["players"]
        if len(players) > 0:
            return "Can't stop the server because people are currently online!"

        self.state = "stopping"

        await self.send_command("stop")
        print("Sent 'stop'. Waiting for graceful shutdown...")

        try:
            await asyncio.wait_for(self._shutdown_event.wait(), timeout=time)
        except asyncio.TimeoutError:
            print("Shutdown timeout. Sending SIGINT.")

        return await self._handle_shutdown()

    async def send_command(self, command: str) -> str | None:
        if self.state == "off":
            return "The server isn't running!"

        if self.process and self.process.stdin:
            print(f"Sending command: {command}")
            self.process.stdin.write((command + "\n").encode())
            await self.process.stdin.drain()

    async def get_online_players(self) -> dict[str, str | list[str]]:
        if self.state != "running":
            return {"error": "The server isn't running!"}

        await self.send_command("list")

        try:
            while True:
                line = await asyncio.wait_for(self.output_queue.get(), timeout=5)

                match = LIST_PATTERN.search(line)
                if match:
                    names = match.group(2).split(", ") if match.group(2) else []
                    return {"players": names}

        except asyncio.TimeoutError:
            return {"error": "Timed out waiting for /list"}
