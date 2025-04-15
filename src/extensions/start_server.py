import arc

from ..server_manager import MCServer

plugin = arc.GatewayPlugin("start_server")


@plugin.include
@arc.slash_command("times_two")
async def times_two(ctx: arc.GatewayContext, num: arc.Option[int, arc.IntParams("give me an integer")]) -> None:
    await ctx.respond(f"{num} times 3 is {num * 3}")

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

@arc.loader
def loader(client: arc.GatewayClient) -> None:
    client.add_plugin(plugin)


@arc.unloader
def unloader(client: arc.GatewayClient) -> None:
    client.remove_plugin(plugin)
