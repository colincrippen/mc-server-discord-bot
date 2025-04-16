import os

import arc
import hikari
from dotenv import load_dotenv

from .server_manager import MCServer

load_dotenv()


bot = hikari.GatewayBot(os.getenv("TOKEN", ""))
client = arc.GatewayClient(bot)

server = MCServer()
client.set_type_dependency(MCServer, server)


client.load_extension("src.extensions.start_server")


@client.include
@arc.slash_command("reload")
async def reload(ctx: arc.GatewayContext) -> None:
    client.unload_extension("src.extensions.start_server")
    client.load_extension("src.extensions.start_server")

    await client.resync_commands()
    await ctx.respond("reloaded")


if __name__ == "__main__":
    if os.name != "nt":
        import asyncio  # noqa: I001
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    bot.run()
