import json

import aiofiles
import arc

from ..server_manager import MCServer

plugin = arc.GatewayPlugin("start_server")


@plugin.include
@arc.slash_command("start", "Starts the server")
async def start_server(ctx: arc.GatewayContext, server: MCServer = arc.inject()) -> None:
    await ctx.respond("Attempting to start the server...")
    response: str = await server.start()
    await ctx.edit_initial_response(response)


@plugin.include
@arc.slash_command("stop", "Closes the server")
async def stop_server(ctx: arc.GatewayContext, server: MCServer = arc.inject()) -> None:
    await ctx.respond("Attempting to stop the server...")
    response: str = await server.stop()
    await ctx.edit_initial_response(response)


@plugin.include
@arc.slash_command("send_command", "sends a command")
async def send_command(
    ctx: arc.GatewayContext,
    my_command: arc.Option[str, arc.StrParams("command pleaseeee")],
    server: MCServer = arc.inject(),
) -> None:
    await ctx.respond("Attempting to send command...")
    response = await server.send_command(my_command)
    if response:
        await ctx.edit_initial_response(response)
    else:
        await ctx.edit_initial_response("Command sent!")


@plugin.include
@arc.slash_command("get_players", "retrieves the number of players")
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
