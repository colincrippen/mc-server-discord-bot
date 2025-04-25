import os

import arc
import hikari
from dotenv import load_dotenv

from .extensions.start_server import update_description, update_players_if_different
from .util.server_manager import MCServer

load_dotenv()


bot = hikari.GatewayBot(os.getenv("TOKEN", ""))
client = arc.GatewayClient(bot)

server = MCServer()
client.set_type_dependency(MCServer, server)


client.load_extension("src.extensions.start_server")


@client.add_startup_hook
@client.inject_dependencies
async def startup(client: arc.GatewayClient, server: MCServer = arc.inject()) -> None:
    await update_description("🛌🛌🛌")
    update_players_if_different.start(client, server)


@client.add_shutdown_hook
async def shutdown(client: arc.GatewayClient) -> None:
    update_players_if_different.stop()
    await update_description("🛌🛌🛌")


# @client.include
# @arc.slash_command("reload")
# async def reload(ctx: arc.GatewayContext) -> None:
#     client.unload_extension("src.extensions.start_server")
#     client.load_extension("src.extensions.start_server")

#     await client.resync_commands()
#     await ctx.respond("reloaded")


if __name__ == "__main__":
    if os.name != "nt":
        import asyncio  # noqa: I001
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    bot.run()
