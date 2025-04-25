import json
import os

import aiofiles
import aiohttp
import arc
import hikari
from hikari.impl.rest import _HTTP_USER_AGENT

from ..util.server_manager import MCServer

plugin = arc.GatewayPlugin("start_server")


def activity(name: str) -> hikari.Activity:
    return hikari.Activity(name=name, type=hikari.ActivityType.CUSTOM)


async def update_description(desc: str) -> str | None:
    target_url = "https://discord.com/api/v10/applications/@me"
    data = {"description": desc}
    headers = {
        "Authorization": f"Bot {os.getenv('TOKEN', '')}",
        "Content-Type": "application/json",
        "User-Agent": _HTTP_USER_AGENT,
    }

    async with aiohttp.ClientSession() as session:  # noqa: SIM117
        async with session.patch(target_url, json=data, headers=headers) as response:
            data = await response.json()
            if "errors" in data:
                return f"Error:\n{json.dumps(data, indent=2)}"


@arc.utils.interval_loop(seconds=10)
async def update_players_if_different(client: arc.GatewayClient) -> None:
    players: list[str]
    async with aiofiles.open("src/online_players.json", "r") as file:
        players = json.loads(await file.read())
        print(f"{players=}")

    new_desc = "Players online: " + ", ".join(players)

    if client.application and client.application.description != new_desc:
        response = await update_description(new_desc)
        if response:
            print(response)
            return

        client.application.description = new_desc
        print("updated description!!!!!")
    else:
        print("descriptions are the same!")


@plugin.listen()
async def startup(event: arc.StartedEvent) -> None:
    await plugin.client.app.update_presence(activity=activity("😴 The server is offline."))


@plugin.include
@arc.slash_command("start", "Starts the server")
async def start_server(ctx: arc.GatewayContext, server: MCServer = arc.inject()) -> None:
    await ctx.respond("Attempting to start the server...")
    await ctx.client.app.update_presence(activity=activity("🛠️ The server is starting up..."))
    response = await server.start()
    await ctx.edit_initial_response(response["msg"])

    if response.get("success"):
        await ctx.respond(f"<@{ctx.user.id}>", user_mentions=True)

    await ctx.client.app.update_presence(activity=activity("⚡️ The server is online!"))


@plugin.include
@arc.slash_command("change_description")
async def change_description(ctx: arc.GatewayContext, desc: arc.Option[str, arc.StrParams()]) -> None:
    """This is hacky and stupid. Do not do this."""
    target_url = "https://discord.com/api/v10/applications/@me"
    data = {"description": desc}
    headers = {
        "Authorization": f"Bot {os.getenv('TOKEN', '')}",
        "Content-Type": "application/json",
        "User-Agent": _HTTP_USER_AGENT,
    }

    async with aiohttp.ClientSession() as session:  # noqa: SIM117
        async with session.patch(target_url, json=data, headers=headers) as response:
            data = await response.json()
            if "errors" in data:
                await ctx.respond(f"❌ Error: ```json\n{json.dumps(data, indent=2)}```")
                return

    await ctx.respond(f"Changed description to {desc}")


@plugin.include
@arc.slash_command("stop", "Closes the server")
async def stop_server(ctx: arc.GatewayContext, server: MCServer = arc.inject()) -> None:
    await ctx.respond("Attempting to stop the server...")
    await ctx.client.app.update_presence(activity=activity("🛠️ The server is shutting down..."))
    response: str = await server.stop()
    await ctx.edit_initial_response(response)
    await ctx.client.app.update_presence(activity=activity("😴 The server is offline."))


# @plugin.include
# @arc.slash_command("send_command", "sends a command")
# async def send_command(
#     ctx: arc.GatewayContext,
#     my_command: arc.Option[str, arc.StrParams("command pleaseeee")],
#     server: MCServer = arc.inject(),
# ) -> None:
#     await ctx.respond("Attempting to send command...")
#     response = await server.send_command(my_command)
#     if response:
#         await ctx.edit_initial_response(response)
#     else:
#         await ctx.edit_initial_response("Command sent!")


@plugin.include
@arc.slash_command("get_players", "Retrieves the number of players")
async def get_players(ctx: arc.GatewayContext, server: MCServer = arc.inject()) -> None:
    await ctx.respond("Fetching player list...")
    response = await server.get_online_players()
    if "error" in response:
        await ctx.edit_initial_response(response["error"])
    else:
        user_map: dict[str, int]
        async with aiofiles.open("src/user_map.json", "r") as file:
            user_map = json.loads(await file.read())

        players = response["players"]
        player_strs = [f"{player} (<@{user_map[player]}>)" if player in user_map else player for player in players]
        num_players = len(players)
        response_str = (
            "There are no players currently online."
            if num_players == 0
            else f"{num_players} online: {', '.join(player_strs)}"
        )

        await ctx.edit_initial_response(response_str, user_mentions=False)


@arc.loader
def loader(client: arc.GatewayClient) -> None:
    client.add_plugin(plugin)


@arc.unloader
def unloader(client: arc.GatewayClient) -> None:
    client.remove_plugin(plugin)
