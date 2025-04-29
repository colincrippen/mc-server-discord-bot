import json
import os
from io import BytesIO

import aiofiles
import aiohttp
import aiosqlite
import arc
import hikari
import numpy as np
from hikari.impl import (
    ContainerComponentBuilder,
    SectionComponentBuilder,
    TextDisplayComponentBuilder,
    ThumbnailComponentBuilder,
)
from hikari.impl.rest import _HTTP_USER_AGENT
from PIL import Image

from ..util.server_manager import SERVER_DIR, MCServer

plugin = arc.GatewayPlugin("start_server")


def custom_activity(name: str) -> hikari.Activity:
    return hikari.Activity(name=name, type=hikari.ActivityType.CUSTOM)


async def update_description(desc: str, aiohttp_client: aiohttp.ClientSession) -> str | None:
    target_url = "https://discord.com/api/v10/applications/@me"
    data = {"description": desc}
    headers = {
        "Authorization": f"Bot {os.getenv('TOKEN', '')}",
        "Content-Type": "application/json",
        "User-Agent": _HTTP_USER_AGENT,
    }

    async with aiohttp_client.patch(target_url, json=data, headers=headers) as response:
        data = await response.json()
        if "errors" in data:
            return f"Error:\n{json.dumps(data, indent=2)}"


@arc.utils.interval_loop(seconds=30)
async def update_players_if_different(
    client: arc.GatewayClient, server: MCServer, aiohttp_client: aiohttp.ClientSession
) -> None:
    players = server.players
    new_desc = (
        (
            f"{len(players)} player{'s' if len(players) > 1 else ''} online:\n```{'\n'.join(players)}```"
            if len(players) > 0
            else "No players online."
        )
        if server.state == "running"
        else "🛌🛌🛌"
    )

    if (
        (server.state == "running" or server.state == "off")
        and client.application
        and client.application.description != new_desc
    ):
        response = await update_description(new_desc, aiohttp_client)
        if response:
            print(response)
            return

        client.application.description = new_desc


@plugin.listen()
async def startup(event: arc.StartedEvent) -> None:
    await plugin.client.app.update_presence(activity=custom_activity("😴 The server is offline."))


@plugin.include
@arc.slash_command("start", "Starts the server")
async def start_server(ctx: arc.GatewayContext, server: MCServer = arc.inject()) -> None:
    await ctx.respond("Attempting to start the server...")
    await ctx.client.app.update_presence(activity=custom_activity("🛠️ The server is starting up..."))
    response = await server.start()
    await ctx.edit_initial_response(response["msg"])

    if response.get("success"):
        await ctx.respond(f"<@{ctx.user.id}>", user_mentions=True)

    await ctx.client.app.update_presence(activity=custom_activity("⚡️ The server is online!"))


@plugin.include
@arc.slash_command("stop", "Closes the server")
async def stop_server(ctx: arc.GatewayContext, server: MCServer = arc.inject()) -> None:
    await ctx.respond("Attempting to stop the server...")
    await ctx.client.app.update_presence(activity=custom_activity("🛠️ The server is shutting down..."))
    response: str = await server.stop()
    await ctx.edit_initial_response(response)
    await ctx.client.app.update_presence(activity=custom_activity("😴 The server is offline."))


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


# @plugin.include
# @arc.slash_command("get_players", "Retrieves the number of players")
# async def get_players(ctx: arc.GatewayContext, server: MCServer = arc.inject()) -> None:
#     await ctx.respond("Fetching player list...")
#     response = await server.get_online_players()
#     if "error" in response:
#         await ctx.edit_initial_response(response["error"])
#     else:
#         user_map: dict[str, int]
#         async with aiofiles.open("src/user_map.json", "r") as file:
#             user_map = json.loads(await file.read())

#         players = response["players"]
#         player_strs = [f"{player} (<@{user_map[player]}>)" if player in user_map else player for player in players]
#         num_players = len(players)
#         response_str = (
#             "There are no players currently online."
#             if num_players == 0
#             else f"{num_players} online: {', '.join(player_strs)}"
#         )

#         await ctx.edit_initial_response(response_str, user_mentions=False)


@plugin.include
@arc.slash_command("get_players", "Retrieves the current players online.")
async def get_players(
    ctx: arc.GatewayContext, server: MCServer = arc.inject(), aiohttp_client: aiohttp.ClientSession = arc.inject()
) -> None:
    response = await server.get_online_players()
    if "error" in response:
        await ctx.respond(response["error"])
        return

    user_map: dict[str, int]
    async with aiofiles.open("src/user_map.json", "r") as file:
        user_map = json.loads(await file.read())

    players: list[str] = response["players"]  # type: ignore
    num_players = len(players)

    if num_players == 0:
        await ctx.respond(component=(TextDisplayComponentBuilder(content="No players online.")))
        return

    player_batches = [players[:4]]
    for i in range(4, num_players, 5):
        player_batches.append(players[i : i + 5])

    for index, batch in enumerate(player_batches):
        components: list[hikari.api.ComponentBuilder] = []
        if index == 0:
            components.append(
                TextDisplayComponentBuilder(content=f"# {num_players} player{'s' if num_players > 1 else ''} online:")
            )
        for player in batch:
            components.append(await create_player_component(player, aiohttp_client, user_map.get(player)))

        await ctx.respond(components=components)


@plugin.include
@arc.slash_command("get_players_v2")
async def get_players_v2(ctx: arc.GatewayContext, server: MCServer = arc.inject()):
    db_path = f"{SERVER_DIR}/playerdata.db"

    async with aiosqlite.connect(db_path) as db:  # noqa: SIM117
        async with db.execute("SELECT * FROM player_info") as cursor:
            async for row in cursor:
                await ctx.respond(row)


async def create_player_component(
    username: str, aiohttp_client: aiohttp.ClientSession, id: int | None = None
) -> ContainerComponentBuilder:
    player_head_url: str = f"https://mc-heads.net/avatar/{username}"
    color_tuple: tuple[int]
    async with aiohttp_client.get(player_head_url) as response:
        img_bytes = await response.read()
        image = Image.open(BytesIO(img_bytes)).convert("RGB")
        image_array = np.array(image)
        average_color = image_array.mean(axis=(0, 1))
        color_tuple = tuple(average_color.astype(int))

    return ContainerComponentBuilder(accent_color=hikari.Color.from_rgb(*color_tuple)).add_component(  # type: ignore
        SectionComponentBuilder(accessory=ThumbnailComponentBuilder(media=player_head_url))
        .add_component(TextDisplayComponentBuilder(content=f"## {username}"))
        .add_component(TextDisplayComponentBuilder(content=f"<@{id}>" if id else "*idk their discord acc lol*"))
    )


@arc.loader
def loader(client: arc.GatewayClient) -> None:
    client.add_plugin(plugin)


@arc.unloader
def unloader(client: arc.GatewayClient) -> None:
    client.remove_plugin(plugin)
