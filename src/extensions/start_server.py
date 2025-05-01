import hashlib
import json
import os
import textwrap
import typing as t
from dataclasses import dataclass
from io import BytesIO

import aiohttp
import aiosqlite
import aiosqlite.cursor
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

DB_PATH = f"{SERVER_DIR}/playerdata.db"


@dataclass
class Player:
    uuid: str
    username: str
    joined_at: str
    currently_online: bool
    deaths: int
    discord_id: t.Optional[str]
    head_color: t.Optional[str]
    head_color_hash: t.Optional[str]


def player_row_factory(cursor: aiosqlite.cursor.Cursor, row: aiosqlite.Row) -> Player:
    return Player(*row)


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


@plugin.include
@arc.slash_command("get_players")
async def get_players(
    ctx: arc.GatewayContext, server: MCServer = arc.inject(), aiohttp_client: aiohttp.ClientSession = arc.inject()
):
    if server.state != "running":
        await ctx.respond("The server is offline.")
        return

    players: list[Player] = []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = player_row_factory  # type: ignore
        async with db.execute("SELECT * FROM player_info WHERE currently_online = 1") as cursor:
            async for player in cursor:
                player = t.cast("Player", player)
                players.append(player)

    num_players = len(players)

    if num_players == 0:
        await ctx.respond("# No players online :frowning2:")
        return

    # each player group has 4 components. 30 % 4 == 7.
    # this leaves two extra components for a header on each page
    player_batches = [players[:7]]
    for i in range(7, num_players, 7):
        player_batches.append(players[i : i + 7])

    for index, batch in enumerate(player_batches):
        components: list[hikari.api.ComponentBuilder] = [
            TextDisplayComponentBuilder(
                content=(
                    f"# {num_players} player{'s' if num_players > 1 else ''} online: "
                    + (f"*(page {index + 1} of {len(player_batches)})*" if len(player_batches) > 1 else "")
                )
            )
        ]
        for player in batch:
            components.append(await create_player_component(aiohttp_client, player))

        await ctx.respond(components=components)


async def create_player_component(aiohttp_client: aiohttp.ClientSession, player: Player) -> ContainerComponentBuilder:
    player_head_url: str = f"https://mc-heads.net/avatar/{player.uuid}"

    async with aiohttp_client.get(player_head_url) as response:
        img_bytes = await response.read()

    new_hash = hashlib.sha256(img_bytes).hexdigest()

    if not player.head_color or new_hash != player.head_color_hash:
        image = Image.open(BytesIO(img_bytes)).convert("RGB")
        image_array = np.array(image)
        average_color = image_array.mean(axis=(0, 1))
        r, g, b = tuple(average_color.astype(int))

        player.head_color = hex(r * 16**4 + g * 16**2 + b)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE player_info SET head_color = ?, head_color_hash = ? WHERE uuid = ?",
                (player.head_color, new_hash, player.uuid),
            )
            await db.commit()

    return ContainerComponentBuilder(accent_color=hikari.Color.from_hex_code(player.head_color)).add_component(
        SectionComponentBuilder(accessory=ThumbnailComponentBuilder(media=player_head_url)).add_component(
            TextDisplayComponentBuilder(
                content=(
                    textwrap.dedent(f"""
                        ## {player.username}
                        {f"<@{player.discord_id}>" if player.discord_id else "*idk their discord acc lol*"}
                        Online since: <t:{player.joined_at}:R>
                        Deaths: `{player.deaths}`
                    """)
                )
            )
        )
    )


@plugin.include
@arc.slash_command("add_mc_username")
async def add_mc_username(
    ctx: arc.GatewayContext, username: arc.Option[str, arc.StrParams("Your minecraft username.")]
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            async with db.execute("SELECT username FROM player_info WHERE username = ?", (username,)) as cursor:
                if not (row := await cursor.fetchone()):
                    await ctx.respond(
                        f"Player `{username}` does not exist! Please log on to the server at least once before running this command!"
                    )
                    return

            await db.execute("UPDATE player_info SET discord_id = NULL WHERE discord_id = ?", (ctx.author.id,))
            await db.execute("UPDATE player_info SET discord_id = ? WHERE username = ?", (ctx.author.id, username))
            await db.commit()

            await ctx.respond(f"Updated Minecraft username to `{row[0]}`!")
        except Exception as _:
            await db.rollback()
            await ctx.respond("An error occurred, username is not updated.")


@arc.loader
def loader(client: arc.GatewayClient) -> None:
    client.add_plugin(plugin)


@arc.unloader
def unloader(client: arc.GatewayClient) -> None:
    client.remove_plugin(plugin)
