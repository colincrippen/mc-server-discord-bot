import arc

plugin = arc.GatewayPlugin("start_server")


@plugin.include
@arc.slash_command("times_two")
async def times_two(ctx: arc.GatewayContext, num: arc.Option[int, arc.IntParams("give me an integer")]) -> None:
    await ctx.respond(f"{num} times 3 is {num * 3}")


@arc.loader
def loader(client: arc.GatewayClient) -> None:
    client.add_plugin(plugin)


@arc.unloader
def unloader(client: arc.GatewayClient) -> None:
    client.remove_plugin(plugin)
