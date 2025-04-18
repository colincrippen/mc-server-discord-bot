import json

import aiofiles
import arc
import hikari

from ..util.server_manager import MCServer

plugin = arc.GatewayPlugin("start_server")


def activity(name: str) -> hikari.Activity:
    return hikari.Activity(name=name, type=hikari.ActivityType.CUSTOM)


@plugin.listen()
async def set_status(event: hikari.StartedEvent) -> None:
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
