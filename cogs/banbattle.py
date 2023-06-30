import asyncio
import random
import re
import traceback
from typing import Any, Coroutine, Union

import discord
from discord.commands import (ApplicationContext, AutocompleteContext, Option,
                              OptionChoice, SlashCommandGroup, slash_command)
from discord.ext import commands
from fuzzy_match import match

from bot import BanBattler
from config.defaults import *
from config.utils import *

SETTINGS = [
    "gamestarter",
    "timetojoin",
    "gametimeout",
    "playerrole",
    "customemoji",
    "selfbanchance",
    "bandm",
    "selfbandm",
    "clear",
]

selfbanchance_min_ = 0
selfbanchance_max_ = 100

timetojoin_min_ = 10
timetojoin_max_ = 120

gametimeout_min_ = 60
gametimeout_max_ = 600


def check_bot_perms(ctx: ApplicationContext, channel: bool = True, **perms):
    if channel:
        my_perms: discord.Permissions = ctx.channel.permissions_for(ctx.guild.me)
    else:
        my_perms: discord.Permissions = ctx.me.guild_permissions

    missing = [
        perm for perm, value in perms.items() if getattr(my_perms, perm) != value
    ]

    if not missing:
        return

    return missing


async def check_perms(ctx: ApplicationContext):
    """Checks permissions"""

    cog: BattlerCog = ctx.cog

    if not ctx.guild:
        await cog.client.on_application_command_error(
            ctx,
            discord.commands.ApplicationCommandInvokeError(commands.NoPrivateMessage()),
        )

        return 0

    first_check_failed = check_bot_perms(
        ctx,
        channel=True,
        send_messages=True,
        add_reactions=True,
        embed_links=True,
        manage_messages=True,
    )

    second_check_failed = check_bot_perms(
        ctx, channel=False, manage_roles=True, manage_channels=True
    )

    if first_check_failed:
        return first_check_failed

    if second_check_failed:
        return second_check_failed

    if (
        ("manage_guild", True) in ctx.author.guild_permissions
        or ("administrator", True) in ctx.author.guild_permissions
        or ctx.author == ctx.guild.owner
        or ctx.author.id in cog.client.owner_ids
    ):
        return 1

    starter = await cog.client.starter.find_one({"_id": ctx.guild.id})
    if starter:
        for role in ctx.author.roles:
            if role.id == starter["role"]:
                return 1

    return -1


async def argument_argument(ctx: AutocompleteContext):
    if not ctx.options["setting"] or not ctx.interaction.guild:
        return []

    setting: str = ctx.options["setting"].lower()

    if setting == "gamestarter" or setting == "playerrole":
        roles_list = ctx.interaction.guild.roles
        roles_list.pop(
            ctx.interaction.guild.roles.index(ctx.interaction.guild.default_role)
        )
        return [
            "{}".format(r.name if r.name.startswith("@") else f"@{r.name}")
            for r in roles_list
            if ctx.value.lower() in r.name.lower()
        ]

    if setting == "timetojoin":
        return (
            [f"Enter a value between {timetojoin_min_} and {timetojoin_max_}"]
            if len(ctx.value) < 1
            else []
        )
    if setting == "gametimeout":
        return (
            [f"Enter a value between {gametimeout_min_} and {gametimeout_max_}"]
            if len(ctx.value) < 1
            else []
        )
    if setting == "selfbanchance":
        return (
            [f"Enter a value between {selfbanchance_min_} and {selfbanchance_max_}"]
            if len(ctx.value) < 1
            else []
        )

    if setting == "bandm":
        return (
            [
                "Enter any string, variables are listed below",
                "{banned_by} - Whoever banned you",
                "{banned_by_id} - The ID of whoever banned you",
                "{banned_by_name} - The name of whoever banned you",
                "{banned_by_discriminator} - The tag [`#1234`] of whoever banned you",
                "{banned_by_mention} - The mention of whoever banned you",
            ]
            if len(ctx.value) < 1
            else []
        )

    if setting == "selfbandm":
        return (
            [
                "Enter any string, variables are listed below",
                "{target} - The target",
                "{target_id} - The ID of the target",
                "{target_name} - The name of the target",
                "{target_discriminator} - The tag [`#1234`] of the target",
                "{target_mention} - The target's mention",
            ]
            if len(ctx.value) < 1
            else []
        )

    if setting == "customemoji":
        return [
            "{}".format(f"<a:{e.name}:{e.id}>" if e.animated else f"<:{e.name}:{e.id}>")
            for e in ctx.bot.emojis
            if ctx.value.lower() in e.name.lower() and e in ctx.interaction.guild.emojis
        ]

    if setting == "clear":
        return [setting for setting in SETTINGS if not setting == "clear"]

    return []


class ReadyOrNot(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        self.timeout = 30
        self.owner = ctx.author
        self.start_game = False
        super().__init__(timeout=self.timeout)

    async def interaction_check(self, interaction: discord.Interaction):
        """Check that determines whether this interaction should be honored"""
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message(
                content=random.choice(CHOICES), ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success)
    async def start(self, button: discord.Button, interaction: discord.Interaction):
        self.start_game = True
        self.clear_items()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, button: discord.Button, interaction: discord.Interaction):
        self.clear_items()
        self.stop()


class GuidePaginator(discord.ui.View):
    def __init__(self, ctx: ApplicationContext, page: int = 0):
        self.pages = GuideEmbeds()
        self.start_page = page
        self.timeout = 120
        self.owner = ctx.author
        self.delete_me = False
        self.expand = False
        self.previous_button = None
        self.ctx = ctx
        self.client: BanBattler = ctx.bot
        self.message: Optional[discord.Message] = None
        super().__init__(timeout=self.timeout)

    async def interaction_check(self, interaction: discord.Interaction):
        """Check that determines whether this interaction should be honored"""
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message(
                content=random.choice(CHOICES), ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        self.clear_items()
        self.stop()

    async def start(self):
        page_list: list[discord.Embed] = [
            self.pages.page_one,
            self.pages.page_two,
            self.pages.page_three,
            self.pages.page_four,
            self.pages.page_five,
            self.pages.page_six,
            self.pages.page_seven,
        ]

        button: discord.Button = self.children[self.start_page]
        button.disabled = True
        self.previous_button = button
        if not self.start_page == 0:
            self.page_one.disabled = False

        inter: discord.Interaction = await self.ctx.respond(
            embed=page_list[self.start_page], view=self
        )
        self.message: discord.InteractionMessage = await inter.original_message()
        self.client.active_paginators.append(self.message)

        return self

    def stop(self):
        self.client.active_paginators.pop(
            self.client.active_paginators.index(self.message)
        )
        super().stop()

    @discord.ui.button(
        label="Home",
        style=discord.ButtonStyle.success,
        emoji="\N{HOUSE BUILDING}",
        disabled=True,
        row=1,
    )
    async def page_one(self, button: discord.Button, interaction: discord.Interaction):
        if self.previous_button:
            self.previous_button.disabled = False

        self.previous_button = button
        button.disabled = True

        await interaction.response.edit_message(embed=self.pages.page_one, view=self)

    @discord.ui.button(
        label="1. What This is", style=discord.ButtonStyle.secondary, row=2
    )
    async def page_two(self, button: discord.Button, interaction: discord.Interaction):
        if self.previous_button:
            self.previous_button.disabled = False

        self.page_one.disabled = False

        self.previous_button = button
        button.disabled = True

        await interaction.response.edit_message(embed=self.pages.page_two, view=self)

    @discord.ui.button(label="2. Gamemodes", style=discord.ButtonStyle.secondary, row=2)
    async def page_three(
        self, button: discord.Button, interaction: discord.Interaction
    ):
        if self.previous_button:
            self.previous_button.disabled = False

        self.page_one.disabled = False

        self.previous_button = button
        button.disabled = True

        await interaction.response.edit_message(embed=self.pages.page_three, view=self)

    @discord.ui.button(label="3. Options", style=discord.ButtonStyle.secondary, row=2)
    async def page_four(self, button: discord.Button, interaction: discord.Interaction):
        if self.previous_button:
            self.previous_button.disabled = False

        self.page_one.disabled = False

        self.previous_button = button
        button.disabled = True

        await interaction.response.edit_message(embed=self.pages.page_four, view=self)

    @discord.ui.button(
        label="4. Customization", style=discord.ButtonStyle.secondary, row=3
    )
    async def page_five(self, button: discord.Button, interaction: discord.Interaction):
        if self.previous_button:
            self.previous_button.disabled = False

        self.page_one.disabled = False

        self.previous_button = button
        button.disabled = True

        await interaction.response.edit_message(embed=self.pages.page_five, view=self)

    @discord.ui.button(label="5. Syntax", style=discord.ButtonStyle.secondary, row=3)
    async def page_six(self, button: discord.Button, interaction: discord.Interaction):
        if self.previous_button:
            self.previous_button.disabled = False

        self.page_one.disabled = False

        self.previous_button = button
        button.disabled = True

        await interaction.response.edit_message(embed=self.pages.page_six, view=self)

    @discord.ui.button(
        label="6. Miscellaneous", style=discord.ButtonStyle.secondary, row=3
    )
    async def page_seven(
        self, button: discord.Button, interaction: discord.Interaction
    ):
        if self.previous_button:
            self.previous_button.disabled = False

        self.page_one.disabled = False

        self.previous_button = button
        button.disabled = True

        await interaction.response.edit_message(embed=self.pages.page_seven, view=self)

    @discord.ui.button(
        label="All Pages",
        style=discord.ButtonStyle.primary,
        emoji="\N{BOOKMARK TABS}",
        row=1,
    )
    async def all_pages(self, button: discord.Button, interaction: discord.Interaction):
        self.clear_items()
        self.expand = True
        self.stop()

    @discord.ui.button(
        label="Close",
        style=discord.ButtonStyle.danger,
        row=1,
        emoji=NewEmote.from_name("<:x_:822656892538191872>"),
    )
    async def close_menu(
        self, button: discord.Button, interaction: discord.Interaction
    ):
        self.delete_me = True
        self.stop()

    # Type-hinting
    page_one: discord.Button
    page_two: discord.Button
    page_three: discord.Button
    page_four: discord.Button
    page_five: discord.Button
    page_six: discord.Button
    page_seven: discord.Button
    all_pages: discord.Button
    close_menu: discord.Button


class BanBattle(BattlerCog):
    def __init__(self, client: BanBattler):
        self.client = client

        self.RoleConverter = commands.RoleConverter()
        self.MemberConverter = commands.MemberConverter()
        self.EmojiConverter = commands.EmojiConverter()

        self.red = "<:redline:859915518638948402>"

        self.players = {}

    async def starter_set_or_no(self, ctx: ApplicationContext) -> list[str]:
        starterRole = await self.client.starter.find_one({"_id": ctx.guild.id})
        if starterRole is not None:
            return [self.client.yes, "<@&{0}>".format(starterRole["role"])]
        else:
            return [self.client.no, " Not set "]

    async def time_set_or_no(self, ctx: ApplicationContext) -> list[str]:
        timeToJoin = await self.client.time_to_join.find_one({"_id": ctx.guild.id})
        if timeToJoin is not None:
            return [self.client.yes, " `{0}s` ".format(timeToJoin["time"])]
        else:
            return [self.client.no, f" Using default (`{DEFAULT_TIME_TO_JOIN}s`) "]

    async def timeout_set_or_no(self, ctx: ApplicationContext) -> list[str]:
        gameTimeout = await self.client.game_timeout.find_one({"_id": ctx.guild.id})
        if gameTimeout is not None:
            return [self.client.yes, " `{0}s` ".format(gameTimeout["time"])]
        else:
            return [self.client.no, f" Using default (`{DEFAULT_GAME_TIMEOUT}s`) "]

    async def player_set_or_no(self, ctx: ApplicationContext) -> list[str]:
        playerRole = await self.client.ban_gamer.find_one({"_id": ctx.guild.id})
        if playerRole is not None:
            return [self.client.yes, "<@&{0}>".format(playerRole["role"])]
        else:
            return [self.client.no, " Not set "]

    async def emoji_set_or_no(self, ctx: ApplicationContext) -> list[str]:
        the_emoji = await self.client.game_emoji.find_one({"_id": ctx.guild.id})
        if the_emoji is not None:
            return [self.client.yes, " " + str(the_emoji["emoji"]) + " "]
        else:
            return [self.client.no, f" Using default (`{DEFAULT_EMOJI}`) "]

    async def selfban_set_or_no(self, ctx: ApplicationContext) -> list[str]:
        the_chance = await self.client.self_ban_chance.find_one({"_id": ctx.guild.id})
        if the_chance is not None:
            return [self.client.yes, " " + str(the_chance["percentage"]) + "% "]
        else:
            return [self.client.no, " Not set "]

    async def dm_set_or_no(self, ctx: ApplicationContext) -> list[str]:
        the_dm = await self.client.ban_dm.find_one({"_id": ctx.guild.id})
        if the_dm is not None:
            return [self.client.yes, ' `"' + str(the_dm["shortened"]) + '"` ']
        else:
            return [self.client.no, " Not set "]

    async def selfban_dm_set_or_no(self, ctx: ApplicationContext) -> list[str]:
        the_selfban_dm = await self.client.self_ban_dm.find_one({"_id": ctx.guild.id})
        if the_selfban_dm is not None:
            return [self.client.yes, ' `"' + str(the_selfban_dm["shortened"]) + '"` ']
        else:
            return [self.client.no, " Not set "]

    async def get_all_bansettings(
        self, ctx: ApplicationContext, key: int = None
    ) -> discord.Embed:
        """
        Returns all the ban battle configurations for the given context
        """

        starter_setting, starter_value = await self.starter_set_or_no(ctx)
        time_setting, time_value = await self.time_set_or_no(ctx)
        timeout_setting, timeout_value = await self.timeout_set_or_no(ctx)
        player_setting, player_value = await self.player_set_or_no(ctx)
        emoji_setting, emoji_value = await self.emoji_set_or_no(ctx)
        chance_setting, chance_value = await self.selfban_set_or_no(ctx)
        dm_setting, dm_value = await self.dm_set_or_no(ctx)
        selfdm_setting, selfdm_value = await self.selfban_dm_set_or_no(ctx)
        embed = discord.Embed(
            description="\n".join(
                [
                    "¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯",
                    f"{'> ' if key == 0 or key == 100 else ''}- {starter_setting } GameStarter: [{                  starter_value}]\n",
                    f"{'> ' if key == 1 or key == 100 else ''}- {time_setting    } TimeToJoin: [{                      time_value}]\n",
                    f"{'> ' if key == 2 or key == 100 else ''}- {timeout_setting } GameTimeout: [{                  timeout_value}]\n",
                    f"{'> ' if key == 3 or key == 100 else ''}- {player_setting  } PlayerRole: [{                    player_value}]\n",
                    f"{'> ' if key == 5 or key == 100 else ''}- {emoji_setting   } CustomEmoji: [{                    emoji_value}]\n",
                    f"{'> ' if key == 7 or key == 100 else ''}- {dm_setting      } BanDM: [{                             dm_value}]\n",
                    f"{'> ' if key == 6 or key == 100 else ''}- {chance_setting  } SelfBanChance (SelfBan Mode): [{  chance_value}]\n",
                    f"{'> ' if key == 8 or key == 100 else ''}- {selfdm_setting  } SelfBanDM (SelfBan Mode): [{      selfdm_value}]",
                    "¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯",
                ]
            ),
            color=self.client.color,
        )
        embed.set_author(
            name=f"Ban Battle settings for {ctx.guild.name}",
            icon_url=ctx.guild.icon or "",
        )
        embed.set_footer(
            text="""
- More info on these settings with /game explain
- Change these settings with /bansettings <setting> <value>
- Reset a setting with /bansettings <setting>
- Or do /bansettings clear to clear all settings
"""
        )
        return embed

    async def end_game(self, guild: discord.Guild) -> None:
        """
        Ends the Ban Battle game in the given guild [:param:`discord.Guild`]
        Parameters
        ------------
        - guild[:class:`discord.Guild`]: The guild's game to end
        """

        num = guild.id
        doc = await self.client.games.find_one({"_id": num})
        channel = guild.get_channel(doc["channel"])
        gamemode = doc["mode"]
        gamer_role = guild.get_role(doc["player_role"])

        try:
            if not gamer_role:
                await self.client.games.delete_one({"_id": guild.id})
                await channel.set_permissions(guild.default_role, send_messages=False)
            starter_role = guild.get_role(doc["starter_role"])
            if starter_role:
                await channel.set_permissions(starter_role, send_messages=True)
            await channel.set_permissions(guild.default_role, send_messages=False)
            await channel.set_permissions(gamer_role, send_messages=None)
            await gamer_role.edit(hoist=False)
            winner = self.players[num][0]
            await channel.send(
                f"<@!{winner.id}> has won the ban battle! Cleaning up this mess..."
            )

            if gamemode in ["classic", "selfban"]:
                guild_bans = await guild.bans()

                for ban in guild_bans:
                    in_game_ban = re.search(
                        r"^Ban battle \(Eliminated by (.)+#[0-9]{4}, User ID: [0-9]{17,}\)$",
                        str(ban.reason),
                    )

                    if in_game_ban:
                        await guild.unban(ban.user, reason="Ban battle unban")

                for member in guild.members:
                    if gamer_role in member.roles:
                        await member.remove_roles(gamer_role)

                await channel.send(
                    "All users from the ban battle are now unbanned (Checking your ban list is still recommended)"
                )

            elif gamemode == "passive":
                for member in guild.members:
                    if gamer_role in member.roles:
                        await member.remove_roles(gamer_role)

                await channel.send(
                    f"I have finished removing the `{gamer_role.name}` role from everyone"
                )

            try:
                await self.players[num][0].remove_roles(gamer_role)
            except KeyError:
                pass

            del self.players[num]
            await self.client.games.delete_one({"_id": guild.id})
        except Exception as e:
            print("".join(traceback.format_exception(e, e, e.__traceback__)))

            await self.client.games.delete_one({"_id": guild.id})
            try:
                del self.players[num]
            except KeyError:
                pass
            await channel.set_permissions(guild.default_role, send_messages=False)
            await channel.set_permissions(gamer_role, send_messages=None)
            for member in guild.members:
                if gamer_role in member.roles:
                    await member.remove_roles(gamer_role)
            embed = discord.Embed(
                title="OOP-",
                description=f'Damn this command **errored**!!!1!!1!11!!!1 Sorry for being a nub, here\'s the error itself, I have cancelled the game in the meantime\n```py\n{"".join(traceback.format_exception(e, e, e.__traceback__))}```\n\n[`Get s0uport`](https://discord.gg/6jC54cRRrm)',
                color=Botcolours.red,
            )
            await channel.send(embed=embed)
            return

    @BattlerCog.listener()
    async def on_ready(self):
        print("BanBattle cog loaded")

    @BattlerCog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        try:
            if before.roles != after.roles and len(before.roles) < len(
                after.roles
            ):  # If it's a role update
                doc = await self.client.ban_gamer.find_one({"_id": before.guild.id})
                if not doc:
                    return

                role: discord.Role = before.guild.get_role(doc["role"])
                if not role:
                    return  # Shouldn't happen

                game = await self.client.games.find_one({"_id": before.guild.id})

                try:
                    self.players[after.guild.id]
                except KeyError:
                    await after.remove_roles(role)

                if game:
                    await after.remove_roles(role)

        except discord.Forbidden:
            pass

    @BattlerCog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            self.players[member.guild.id]
            self.players[member.guild.id].index(member)
        except (
            KeyError,
            ValueError,
        ):
            return

        doc = await self.client.games.find_one({"_id": member.guild.id})
        if not doc:
            self.players[member.guild.id].pop(
                self.players[member.guild.id].index(member)
            )
            return

        try:
            self.players[member.guild.id].pop(
                self.players[member.guild.id].index(member)
            )
        except (
            KeyError,
            ValueError,
        ):
            pass
        if doc["mode"] in ["classic", "selfban"]:
            try:
                await member.ban(
                    reason=f"Ban battle (Eliminated by {self.client.user.name}#{self.client.user.discriminator}, User ID: {self.client.user.id})",
                )
            except Exception:
                pass
        if len(self.players[member.guild.id]) <= 1:
            await self.end_game(member.guild)
        return

    game = SlashCommandGroup("game", "Game-related commands")

    @game.command(
        name="explain",
        description="Give a rundown on how everything works",
    )
    @commands.max_concurrency(1, commands.BucketType.guild, wait=False)
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def explain(
        self,
        ctx: ApplicationContext,
        page: Option(
            int,
            name="page",
            description="The page to jump to",
            choices=[
                OptionChoice(name="Page 1 (What This is)", value=1),
                OptionChoice(name="Page 2 (Gamemodes)", value=2),
                OptionChoice(name="Page 3 (Options)", value=3),
                OptionChoice(name="Page 4 (Customization)", value=4),
                OptionChoice(name="Page 5 (Syntax)", value=5),
                OptionChoice(name="Page 6 (Misc.)", value=6),
            ],
            required=False,
        ) = 0,
    ):
        view = GuidePaginator(ctx=ctx, page=page)
        pages = GuideEmbeds()

        await view.start()

        await view.wait()
        if view.delete_me:
            await view.message.delete()

        elif view.expand:
            await view.message.edit(
                embeds=[
                    pages.page_two,
                    pages.page_three,
                    pages.page_four,
                    pages.page_five,
                    pages.page_six,
                    pages.page_seven,
                ],
                view=None,
            )

        else:
            try:
                await view.message.edit(view=None)
            except Exception:
                pass

        return

    @game.command(name="start", description="Start a Ban Battle game")
    @commands.max_concurrency(1, commands.BucketType.guild, wait=False)
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def start(
        self,
        ctx: ApplicationContext,
        gamemode: Option(
            str,
            name="gamemode",
            description="The variant of Ban Battles you want to play",
            choices=[
                OptionChoice(name="Classic", value="classic"),
                OptionChoice(name="Passive", value="passive"),
                OptionChoice(name="SelfBan", value="selfban"),
            ],
        ),
        pingrole: Option(
            discord.Role,
            name="ping",
            description="Ping a role",
            required=False,
        ) = None,
        role: Option(
            discord.Role,
            name="role",
            description="A requirement role users must have to participate",
            required=False,
        ) = None,
    ):
        # Permission Checking
        check_result = await check_perms(ctx)
        if check_result == 0:
            return

        if check_result == -1:
            raise commands.MissingPermissions(["manage_guild"])

        if isinstance(check_result, list):
            raise commands.BotMissingPermissions(check_result)

        # Type-hinting
        guild: discord.Guild = ctx.guild
        channel: discord.TextChannel = ctx.channel
        bot_role = guild.self_role or guild.me.top_role

        pingrole: discord.Role = pingrole
        role: discord.Role = role

        async def handle_error(e: Exception, gamer_role: discord.Role):
            print("".join(traceback.format_exception(e, e, e.__traceback__)))
            await self.client.games.delete_one({"_id": guild.id})
            try:
                del self.players[num]
            except KeyError:
                pass
            if ("manage_roles", True) in list(guild.me.guild_permissions):
                await channel.set_permissions(guild.default_role, send_messages=False)
                await channel.set_permissions(gamer_role, send_messages=None)
                for member in guild.members:
                    if gamer_role in member.roles:
                        await member.remove_roles(gamer_role)
            embed = discord.Embed(
                title="OOP-",
                description=f'If the error below says something like "Missing Permissions", try giving me admin and making sure my role is above the player\'s role\n```py\n{"".join(traceback.format_exception(e, e, e.__traceback__))}```\n\n[`Get s0uport`](https://discord.gg/6jC54cRRrm)',
                color=Botcolours.red,
            )
            await ctx.send_followup(embed=embed)

            try:
                wh: discord.Webhook = await self.client.fetch_webhook(
                    906418291092897813
                )
                await wh.send(
                    "\n".join(
                        [
                            f"Guild Name: {guild.name}",
                            f"Guild ID: {guild.id}",
                            f"Gamemode: {gamemode}",
                            f"```py",
                            "Bot role position:",
                            f"{guild.self_role.position}",
                            "Gamer role position:",
                            f"{gamer_role.position}",
                            f"Bot permissions:",
                            "",
                            "\n".join(
                                [p[0] for p in guild.me.guild_permissions if p[1]]
                            ),
                            f"```",
                            f"```py",
                            f"Traceback:",
                            "",
                            f"{''.join(traceback.format_exception(e, e, e.__traceback__))}",
                            f"```",
                        ]
                    )
                )
            except Exception as e:
                print("".join(traceback.format_exception(e, e, e.__traceback__)))
            return

        try:
            await channel.set_permissions(
                bot_role,
                send_messages=True,
                embed_links=True,
            )
            pweafix = "/"
            num = guild.id
            starter: Union[dict, None] = await self.client.starter.find_one(
                {"_id": num}
            )

            gamer: Union[dict, None] = await self.client.ban_gamer.find_one(
                {"_id": num}
            )
            if not gamer:
                embed = discord.Embed(
                    title="Yeah, so uhhh",
                    description=f"Looks like you don't have a player role set up, you can do that now with\n[`/bansettings`]",
                    color=Botcolours.red,
                )
                await ctx.send_response(embed=embed, ephemeral=True)
                ctx.command.reset_cooldown(ctx)
                return

            gamer_role = await self.RoleConverter.convert(ctx, str(gamer["role"]))

            if bot_role.position < gamer_role.position:
                thing = await self.player_set_or_no(ctx)
                embed = discord.Embed(
                    title="Yeah, so uhhh",
                    description="Looks like my bot role is below the set player role, which I need control over.\nTo fix this, simply move my bot role [<@&{0}>] **above** the player role [{1}]".format(
                        bot_role.id, thing[1]
                    ),
                    color=Botcolours.red,
                )
                await ctx.send_response(
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(
                        roles=False, replied_user=True
                    ),
                    ephemeral=True,
                )
                ctx.command.reset_cooldown(ctx)
                return

            if bot_role.position < 2:
                thingy = await self.player_set_or_no(ctx)
                embed = discord.Embed(
                    title="Yeah, so uhhh",
                    description=f"Looks like my bot role is set to the @everyone role in the server.\n To fix this, simply make me a role (any name works), with the same permissions, and drag it **above** [{thingy[1]}]",
                    color=Botcolours.red,
                )
                await ctx.send_response(
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(
                        everyone=False, replied_user=True
                    ),
                    ephemeral=True,
                )
                ctx.command.reset_cooldown(ctx)
                return

            self.players[num] = []
            gamemode = gamemode.lower()

            if gamemode not in ["classic", "passive", "selfban"]:
                await ctx.send_response(
                    content=f"There's currently 3 types of gamemodes, `classic`, `selfban`,  and `passive`. You can see more on these with `/game explain`"
                )
                ctx.command.reset_cooldown(ctx)
                return

            if gamemode in ["classic", "selfban"] and (
                "ban_members",
                True,
            ) not in list(ctx.me.guild_permissions):
                await self.start_error(
                    ctx, error=commands.BotMissingPermissions(["ban_members"])
                )
                ctx.command.reset_cooldown(ctx)
                return

            selfban_dm = None
            banned_message = None
            ban_dm: Union[dict, None] = await self.client.ban_dm.find_one(
                {"_id": guild.id}
            )

            if ban_dm:
                banned_message: str = ban_dm["message"]
                BANNED_MESSAGE: str = banned_message

            if gamemode == "selfban":
                selfbanchance: Union[
                    dict, None
                ] = await self.client.self_ban_chance.find_one({"_id": num})
                if not selfbanchance:
                    embed = discord.Embed(
                        title="Yeah, so uhhh",
                        description=f"If you wanna play SelfBan Mode, you need to set a percentage of how often you'll end up banning yourself [`/bset selfbanchance`]",
                        color=Botcolours.red,
                    )
                    await ctx.send_response(embed=embed, ephemeral=True)
                    ctx.command.reset_cooldown(ctx)
                    return
                selfban_dm: Union[dict, None] = await self.client.self_ban_dm.find_one(
                    {"_id": guild.id}
                )
                if selfban_dm:
                    selfbanned_message: str = selfban_dm["message"]
                    SELFBANNED_MESSAGE: str = selfbanned_message
                selfbanpercent: int = selfbanchance["percentage"]
                otherpercent: int = 100 - selfbanpercent

            embed = discord.Embed(
                title="🔨 Ban Battle event! 🔨 {0}".format(
                    "[No Bans]"
                    if gamemode == "passive"
                    else f"[{selfbanpercent}% Chance of self-bans]"
                    if gamemode == "selfban"
                    else ""
                ),
                url="https://www.youtube.com/watch?v=Q9G9KoAgEdM",
                description="\n".join(
                    [
                        "",
                        "{0} PLAYERS {0}".format(self.red * 2),
                        "> Simply **@Someone to {0} them**".format(
                            "ban" if gamemode in ["classic", "selfban"] else "eliminate"
                        ),
                        "> **React** with the emoji below to join",
                        "> Use the **/lp** command to view all the players",
                        "{0}".format(self.red * 7),
                        "",
                        "▬▬ HOSTS ▬▬",
                        "> Follow my instructions while I set up the game",
                    ]
                ),
                color=0x2E3135,
            )
            embed.set_thumbnail(
                url="https://cdn.discordapp.com/emojis/859940874028056606.gif?v=1"
            )
            embed.set_footer(text="Send 'CANCEL' to cancel")

            if gamemode in ["classic", "selfban"]:
                embed.description += f"\n\n**NOTE: THIS GAMEMODE __WILL__ BAN PEOPLE, IF THAT ISN'T WHAT YOU WANT, CONSIDER PASSIVE MODE**"

            role = role or guild.default_role

            if not role == guild.default_role:
                embed.description += (
                    f"\n\n**MUST HAVE THE {role.mention} ROLE TO JOIN**"
                )

            ongoing: Union[dict, None] = await self.client.games.find_one(
                {"_id": guild.id}
            )

            if ongoing:
                await ctx.send_response(
                    content="You already have an ongoing game in this server!",
                    ephemeral=True,
                )
                return

            if pingrole and ("mention_everyone", True) not in list(
                guild.me.guild_permissions
            ):
                await self.start_error(
                    ctx,
                    error=commands.BotMissingPermissions(["mention_everyone"]),
                )
                ctx.command.reset_cooldown(ctx)
                return

            await ctx.defer()
            msg: discord.Message = await ctx.send_followup(
                embed=embed,
                allowed_mentions=discord.AllowedMentions(roles=True, everyone=True),
            )

            if pingrole:
                await msg.edit(content=f"{pingrole.mention}")

            the_emoji: Union[dict, None] = await self.client.game_emoji.find_one(
                {"_id": guild.id}
            )
            if the_emoji:
                try:
                    await msg.add_reaction(f"{the_emoji['emoji']}")
                except discord.HTTPException:
                    await self.client.game_emoji.delete_one({"_id": guild.id})
                    await msg.add_reaction(DEFAULT_EMOJI)
            else:
                await msg.add_reaction(DEFAULT_EMOJI)

            the_time: Union[dict, None] = await self.client.time_to_join.find_one(
                {"_id": guild.id}
            )
            the_time_to_join: int = (
                the_time["time"] if the_time else DEFAULT_TIME_TO_JOIN
            )
            the_timeout: Union[dict, None] = await self.client.game_timeout.find_one(
                {"_id": guild.id}
            )
            the_game_timeout = (
                the_timeout["time"] if the_timeout else DEFAULT_GAME_TIMEOUT
            )

            def check(m: discord.Message) -> bool:
                return m.content.lower() == "cancel" and m.channel == channel

            while True:
                try:
                    cancel = await self.client.wait_for(
                        "message", timeout=the_time_to_join, check=check
                    )

                    if cancel:
                        await msg.edit(
                            embed=discord.Embed(
                                description="Game cancelled", color=0xFF0000
                            )
                        )
                        try:
                            await msg.clear_reactions()
                        except discord.HTTPException:
                            pass
                        await cancel.reply(content="Game cancelled")
                        ctx.command.reset_cooldown(ctx)
                        return

                except asyncio.TimeoutError:
                    break

            async def get_reacts(m: discord.Message):
                message: discord.Message = await channel.fetch_message(m.id)
                a_list = await message.reactions[0].users().flatten()
                try:
                    a_list.pop(a_list.index(self.client.user))
                except ValueError:
                    pass
                return a_list

            participants = await get_reacts(msg)

            if len(participants) <= 1 or type(participants) != list:
                await msg.reply(
                    content="The game has been cancelled due to a lack of players"
                )
                try:
                    await msg.clear_reactions()
                except discord.HTTPException:
                    pass
                await msg.edit(
                    embed=discord.Embed(description="Game cancelled", color=0xFF0000)
                )
                ctx.command.reset_cooldown(ctx)
                return

            embed = discord.Embed(description="Setting up the game...")
            to_edit: discord.Message = await ctx.send(content=None, embed=embed)
            try:
                await msg.clear_reactions()
            except discord.HTTPException:
                pass

            counter = 0

            for user in participants:
                try:
                    member = await self.MemberConverter.convert(ctx, str(user.id))
                except commands.BadArgument:
                    continue

                if member not in guild.members or member.bot:
                    continue

                if role != guild.default_role and role in member.roles:
                    self.players[num].append(member)
                    counter += 1

                elif role == guild.default_role:
                    self.players[num].append(member)
                    counter += 1

                else:
                    continue

            if counter <= 1:
                for member in guild.members:
                    if gamer_role in member.roles:
                        await member.remove_roles(gamer_role)
                if role == guild.default_role:
                    await msg.reply(
                        content="There's like not enough people for the game..."
                    )
                else:
                    await msg.reply(
                        content="There aren't enough people with the required role ._."
                    )
                ctx.command.reset_cooldown(ctx)
                return

            async with ctx.typing():
                if gamer_role.position > 1:
                    await gamer_role.edit(position=bot_role.position - 1, hoist=True)

                else:
                    await gamer_role.edit(hoist=True)

                for member in self.players[num]:
                    await member.add_roles(gamer_role)
                    await asyncio.sleep(0.5)

                for member in guild.members:
                    if member not in self.players[num] and gamer_role in member.roles:
                        await member.remove_roles(gamer_role)
                        await asyncio.sleep(5)

                await self.client.games.insert_one(
                    {
                        "_id": guild.id,
                        "channel": channel.id,
                        "guild": guild.id,
                        "mode": gamemode,
                        "player_role": gamer_role.id,
                        "starter_role": starter["role"]
                        if starter
                        else 000000000000000000,
                    }
                )

            embed = discord.Embed(
                description="Everything's ready! Click start to start whenever you're ready (or cancel to cancel)",
                color=Botcolours.green,
            )
            view = ReadyOrNot(ctx=ctx)
            delete_view: discord.Message = await to_edit.edit(embed=embed, view=view)

            timed_out = await view.wait()

            if timed_out is True:
                still_ongoing: Union[dict, None] = await self.client.games.find_one(
                    {"_id": guild.id}
                )
                if not still_ongoing:
                    return
                await self.client.games.delete_one({"_id": guild.id})
                await delete_view.delete()
                await msg.edit(
                    embed=discord.Embed(
                        description="The signal to start was never recieved. Ending the command",
                        color=Botcolours.red,
                    )
                )
                for member in self.players[num]:
                    await member.remove_roles(gamer_role)

                del self.players[num]
                return

            elif view.start_game is True:
                still_ongoing: Union[dict, None] = await self.client.games.find_one(
                    {"_id": guild.id}
                )
                if still_ongoing:
                    await channel.set_permissions(
                        guild.default_role, send_messages=False
                    )
                    if len(self.players[num]) == 1:
                        await self.end_game(guild)
                        return
                    await channel.set_permissions(gamer_role, send_messages=True)
                    await delete_view.edit(view=None)
                    await ctx.send(
                        f"Go! The channel has been unlocked for those with the `{role.name}` role"
                    )

            elif view.start_game is False:
                still_ongoing: Union[dict, None] = await self.client.games.find_one(
                    {"_id": guild.id}
                )
                if not still_ongoing:
                    return
                await self.client.games.delete_one({"_id": guild.id})
                await delete_view.delete()
                await msg.edit(
                    embed=discord.Embed(
                        description="Game cancelled", color=Botcolours.red
                    )
                )
                for member in self.players[num]:
                    await member.remove_roles(gamer_role)

                del self.players[num]
                return

            def check(m: discord.Message) -> bool:
                return (
                    m.channel == channel
                    and gamer_role in m.author.roles
                    and m.author in self.players[num]
                    and re.search(r"(<@!?[^&])?\d{17,}>?", m.content) is not None
                )

            while True:
                try:
                    the_ban_message: discord.Message = await self.client.wait_for(
                        "message", timeout=the_game_timeout, check=check
                    )

                    if the_ban_message:
                        try:
                            macth = re.search(
                                r"(<@!?[^&])?\d{17,}>?", the_ban_message.content
                            )
                            member: discord.Member = await self.MemberConverter.convert(
                                ctx, str(macth[0])
                            )

                        except commands.BadArgument:
                            continue

                        if gamemode in ["classic", "selfban"]:
                            if (
                                gamer_role in member.roles
                                and member in self.players[num]
                            ):
                                original_member = member
                                if gamemode == "selfban":
                                    le_choices = random.choices(
                                        population=[
                                            the_ban_message.author,
                                            member,
                                        ],
                                        weights=(selfbanpercent, otherpercent),
                                        k=20,
                                    )
                                    member = le_choices[0]
                                try:
                                    sent = False
                                    if (
                                        gamemode == "selfban"
                                        and member.id == the_ban_message.author.id
                                        and selfban_dm is not None
                                    ):
                                        selfbanned_message = selfbanned_message.replace(
                                            r"{target}",
                                            f"{original_member.name}#{original_member.discriminator}",
                                        )
                                        selfbanned_message = selfbanned_message.replace(
                                            r"{target_id}",
                                            f"{original_member.id}",
                                        )
                                        selfbanned_message = selfbanned_message.replace(
                                            r"{target_name}",
                                            f"{original_member.name}",
                                        )
                                        selfbanned_message = selfbanned_message.replace(
                                            r"{target_discriminator}",
                                            f"{original_member.discriminator}",
                                        )
                                        selfbanned_message = selfbanned_message.replace(
                                            r"{target_mention}",
                                            f"{original_member.mention}",
                                        )
                                        await member.send(selfbanned_message)
                                        selfbanned_message = SELFBANNED_MESSAGE
                                        sent = True
                                    if banned_message is not None and sent == False:
                                        banned_message = banned_message.replace(
                                            r"{banned_by}",
                                            f"{the_ban_message.author.name}#{the_ban_message.author.discriminator}",
                                        )
                                        banned_message = banned_message.replace(
                                            r"{banned_by_id}",
                                            f"{the_ban_message.author.id}",
                                        )
                                        banned_message = banned_message.replace(
                                            r"{banned_by_name}",
                                            f"{the_ban_message.author.name}",
                                        )
                                        banned_message = banned_message.replace(
                                            r"{banned_by_discriminator}",
                                            f"{the_ban_message.author.discriminator}",
                                        )
                                        banned_message = banned_message.replace(
                                            r"{banned_by_mention}",
                                            f"{the_ban_message.author.mention}",
                                        )
                                        await member.send(banned_message)
                                        banned_message = BANNED_MESSAGE
                                except discord.HTTPException:
                                    pass
                                try:
                                    await member.ban(
                                        reason=f"Ban battle (Eliminated by {the_ban_message.author.name}#{the_ban_message.author.discriminator}, User ID: {the_ban_message.author.id})",
                                        delete_message_days=0,
                                    )
                                    try:
                                        self.players[num].pop(
                                            self.players[num].index(member)
                                        )
                                    except (ValueError, KeyError):
                                        pass
                                except discord.Forbidden:
                                    await member.remove_roles(
                                        gamer_role,
                                        reason="Ban battle elimination (Couldn't ban them)",
                                    )
                                    try:
                                        self.players[num].pop(
                                            self.players[num].index(member)
                                        )
                                    except (ValueError, KeyError):
                                        pass
                                    await the_ban_message.add_reaction(self.client.yes)
                                    if len(self.players[num]) <= 1:
                                        await self.end_game(guild)
                                        return
                                await the_ban_message.add_reaction(self.client.yes)
                                if len(self.players[num]) <= 1:
                                    return
                            else:
                                await the_ban_message.add_reaction(self.client.no)

                        elif gamemode == "passive":
                            if (
                                gamer_role in member.roles
                                and member in self.players[num]
                            ):
                                await member.remove_roles(
                                    gamer_role,
                                    reason=f"Ban battle (Eliminated by {the_ban_message.author.name}#{the_ban_message.author.discriminator}, User ID: {the_ban_message.author.id})",
                                )
                                try:
                                    self.players[num].pop(
                                        self.players[num].index(member)
                                    )
                                except (ValueError, KeyError):
                                    pass
                                try:
                                    if banned_message is not None:
                                        banned_message = banned_message.replace(
                                            r"{banned_by}",
                                            f"{the_ban_message.author.name}#{the_ban_message.author.discriminator}",
                                        )
                                        banned_message = banned_message.replace(
                                            r"{banned_by_id}",
                                            f"{the_ban_message.author.id}",
                                        )
                                        banned_message = banned_message.replace(
                                            r"{banned_by_name}",
                                            f"{the_ban_message.author.name}",
                                        )
                                        banned_message = banned_message.replace(
                                            r"{banned_by_discriminator}",
                                            f"{the_ban_message.author.discriminator}",
                                        )
                                        banned_message = banned_message.replace(
                                            r"{banned_by_mention}",
                                            f"{the_ban_message.author.mention}",
                                        )
                                        await member.send(banned_message)
                                        banned_message = BANNED_MESSAGE
                                except discord.HTTPException:
                                    pass
                                await the_ban_message.add_reaction(self.client.yes)
                            else:
                                await the_ban_message.add_reaction(self.client.no)

                            if len(self.players[num]) == 1:
                                await self.end_game(guild)
                                return
                            else:
                                continue

                except asyncio.TimeoutError:
                    still_ongoing: Union[dict, None] = await self.client.games.find_one(
                        {"_id": guild.id}
                    )
                    if not still_ongoing:
                        return
                    await self.client.games.delete_one({"_id": guild.id})
                    del self.players[num]
                    await ctx.send(
                        "Hmmm, looks like a dead game, imma end it here then, thanks for playing!"
                    )
                    await channel.set_permissions(
                        guild.default_role, send_messages=False
                    )
                    await channel.set_permissions(gamer_role, send_messages=None)
                    for member in guild.members:
                        if gamer_role in member.roles:
                            await member.remove_roles(gamer_role)
                    return

        except Exception as e:
            await handle_error(e, gamer_role)
            ctx.command.reset_cooldown(ctx)
            return

    @slash_command(name="lp", description="Lists all the players in a Ban Battle game")
    @commands.guild_only()
    async def listplayers(self, ctx: ApplicationContext):
        num = ctx.guild.id
        List = []
        for i in range(0, 201):
            try:
                List.append(self.players[num][i].mention)
            except Exception:
                break
        if List == []:
            await ctx.respond(
                "There is currently no active ban battle game!", ephemeral=True
            )
        else:
            embed = discord.Embed(
                title="List of players",
                description=" ".join(List),
                color=Botcolours.yellow,
            )
            await ctx.respond(embed=embed)
        return

    @slash_command(
        name="bansettings", description="Commands related to game configurations"
    )
    @commands.guild_only()
    async def bansettings(
        self,
        ctx: ApplicationContext,
        setting: Option(
            str,
            name="setting",
            description="The setting you want to change",
            required=False,
            choices=[
                OptionChoice("Game starter", "gamestarter"),
                OptionChoice("Time to join", "timetojoin"),
                OptionChoice("Game timeout", "gametimeout"),
                OptionChoice("Player role", "playerrole"),
                OptionChoice("Custom emoji", "customemoji"),
                OptionChoice("Selfban chance", "selfbanchance"),
                OptionChoice("Ban DM", "bandm"),
                OptionChoice("Selfban DM", "selfbandm"),
                OptionChoice("Clear", "clear"),
            ],
        ) = None,
        argument: Option(
            str,
            name="argument",
            description="The argument for that setting (leave blank to remove)",
            required=False,
            autocomplete=argument_argument,
        ) = None,
    ):
        # Typehinting
        setting: str = setting
        argument: str = argument

        if (
            not setting
            and not argument
            or argument
            and not setting
            or setting not in SETTINGS
        ):
            try:
                await ctx.defer()
                embed = await self.get_all_bansettings(ctx)
                await ctx.send_followup(embed=embed, ephemeral=False)
                return
            except Exception as e:
                print("".join(traceback.format_exception(e, e, e.__traceback__)))
                return

        if ("manage_guild", True) in ctx.author.guild_permissions:
            if setting == "gamestarter":
                the_role = None
                roles_list = ctx.guild.roles
                roles_list.pop(ctx.guild.roles.index(ctx.guild.default_role))
                if argument:
                    try:
                        the_role = await self.RoleConverter.convert(ctx, argument)
                    except commands.BadArgument:
                        mach: list[discord.Role, int] = match.extractOne(
                            argument, roles_list
                        )
                        if mach[1] < 0.2:
                            return await ctx.send_response(
                                "Couldn't find a role using the query given",
                                ephemeral=True,
                            )
                        the_role = mach[0]

                await ctx.defer()
                return await self.gamestarter(ctx, the_role)

            if setting == "timetojoin":
                arg = None
                try:
                    if argument:
                        arg = int(argument)
                        assert arg >= timetojoin_min_ and arg <= timetojoin_max_

                except Exception:
                    return await ctx.send_response(
                        f"Please enter an integer between {timetojoin_min_} and {timetojoin_max_}!",
                        ephemeral=True,
                    )

                else:
                    await ctx.defer()
                    return await self.timetojoin(ctx, arg)

            if setting == "gametimeout":
                arg = None
                try:
                    if argument:
                        arg = int(argument)
                        assert arg >= gametimeout_min_ and arg <= gametimeout_max_

                except Exception:
                    return await ctx.send_response(
                        f"Please enter an integer between {gametimeout_min_} and {gametimeout_max_}!",
                        ephemeral=True,
                    )

                else:
                    await ctx.defer()
                    return await self.gametimeout(ctx, arg)

            if setting == "playerrole":
                the_role = None
                roles_list = ctx.guild.roles
                roles_list.pop(ctx.guild.roles.index(ctx.guild.default_role))
                if argument:
                    try:
                        the_role = await self.RoleConverter.convert(ctx, argument)
                    except commands.BadArgument:
                        mach: list[discord.Role, int] = match.extractOne(
                            argument, roles_list
                        )
                        if mach[1] < 0.2:
                            return await ctx.send_response(
                                "Couldn't find a role using the query given",
                                ephemeral=True,
                            )
                        the_role = mach[0]

                await ctx.defer()
                return await self.playerrole(ctx, the_role)

            if setting == "customemoji":
                if not ("external_emojis", True) in ctx.guild.me.guild_permissions:
                    embed = discord.Embed(
                        title="Yeah, so uhhh",
                        description="I need external emoji permissions for this feature :|",
                        color=Botcolours.red,
                    )
                    return await ctx.send_response(embed=embed, ephemeral=True)

                await ctx.defer()
                return await self.customemoji(ctx, argument)

            if setting == "selfbanchance":
                arg = None
                try:
                    if argument:
                        arg = int(argument)
                        assert arg >= selfbanchance_min_ and arg <= selfbanchance_max_

                except Exception:
                    return await ctx.send_response(
                        f"Please enter an integer between {selfbanchance_min_} and {selfbanchance_max_}!",
                        ephemeral=True,
                    )

                else:
                    await ctx.defer()
                    return await self.selfbanchance(ctx, arg)

            if setting == "bandm":
                await ctx.defer()
                return await self.bandm(ctx, argument)

            if setting == "selfbandm":
                await ctx.defer()
                return await self.selfbandm(ctx, argument)

            if setting == "clear":
                if (
                    not argument
                    or argument
                    and argument not in SETTINGS
                    or argument == "clear"
                ):
                    return await self.clear(ctx)

                action: Coroutine[Any, Any, None] = getattr(self, argument)

                await ctx.defer()
                return await action(ctx)

        else:
            raise commands.MissingPermissions(["manage_guild"])

    async def gamestarter(self, ctx: ApplicationContext, role: discord.Role = None):
        if not role:
            try:
                await self.client.starter.delete_one({"_id": ctx.guild.id})
            except Exception:
                pass
            embed = await self.get_all_bansettings(ctx, key=0)
            await ctx.send_followup(
                content=f"{self.client.yes} Game Starter successfully reset",
                embed=embed,
                ephemeral=False,
            )
            return

        await self.client.starter.update_one(
            {"_id": ctx.guild.id},
            {"$set": {"_id": ctx.guild.id, "role": role.id}},
            upsert=True,
        )

        embed = await self.get_all_bansettings(ctx, key=0)
        await ctx.send_followup(
            content=f"{self.client.yes} Game Starter successfully updated to `{role.name}`",
            embed=embed,
            ephemeral=False,
            allowed_mentions=discord.AllowedMentions(roles=False),
        )
        return

    async def timetojoin(self, ctx: ApplicationContext, time: int = None):
        if not time:
            try:
                await self.client.time_to_join.delete_one({"_id": ctx.guild.id})
            except Exception:
                pass
            embed = await self.get_all_bansettings(ctx, key=1)
            await ctx.send_followup(
                content=f"{self.client.yes} Time to join successfully reset",
                embed=embed,
                ephemeral=False,
            )
            return

        await self.client.time_to_join.update_one(
            {"_id": ctx.guild.id},
            {"$set": {"_id": ctx.guild.id, "time": time}},
            upsert=True,
        )

        embed = await self.get_all_bansettings(ctx, key=1)
        await ctx.send_followup(
            content=f"{self.client.yes} Time to join successfully updated to `{time}` seconds",
            embed=embed,
            ephemeral=False,
        )
        return

    async def gametimeout(self, ctx: ApplicationContext, time: int = None):
        if not time:
            try:
                await self.client.game_timeout.delete_one({"_id": ctx.guild.id})
            except Exception:
                pass
            embed = await self.get_all_bansettings(ctx, key=2)
            await ctx.send_followup(
                content=f"{self.client.yes} Time to join successfully reset",
                embed=embed,
            )
            return
        await self.client.game_timeout.update_one(
            {"_id": ctx.guild.id},
            {"$set": {"_id": ctx.guild.id, "time": time}},
            upsert=True,
        )
        embed = await self.get_all_bansettings(ctx, key=2)
        await ctx.send_followup(
            content=f"{self.client.yes} Time to join successfully updated to `{time}` seconds",
            embed=embed,
        )
        return

    async def playerrole(self, ctx: ApplicationContext, role: discord.Role = None):
        if not role:
            try:
                await self.client.ban_gamer.delete_one({"_id": ctx.guild.id})
            except Exception:
                pass
            embed = await self.get_all_bansettings(ctx, key=3)
            await ctx.send_followup(
                content=f"{self.client.yes} Player Role successfully reset", embed=embed
            )
            return

        await self.client.ban_gamer.update_one(
            {"_id": ctx.guild.id},
            {"$set": {"_id": ctx.guild.id, "role": role.id}},
            upsert=True,
        )

        embed = await self.get_all_bansettings(ctx, key=3)
        await ctx.send_followup(
            content=f"{self.client.yes} Player Role successfully updated to `{role.name}`",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=False),
        )
        return

    async def customemoji(self, ctx: ApplicationContext, emoji: str = None):
        if not emoji:
            try:
                await self.client.game_emoji.delete_one({"_id": ctx.guild.id})
            except Exception:
                pass
            embed = await self.get_all_bansettings(ctx, key=5)
            return await ctx.send_followup(
                content=f"{self.client.yes} Custom emoji successfully reset",
                embed=embed,
            )
        try:
            emoji = await self.EmojiConverter.convert(ctx, emoji)
        except commands.EmojiNotFound:
            if len(emoji) > 1:
                return await ctx.send_followup(
                    "Either that isn't a valid emoji or I can't access it",
                    ephemeral=True,
                )
        await self.client.game_emoji.update_one(
            {"_id": ctx.guild.id},
            {"$set": {"_id": ctx.guild.id, "emoji": str(emoji)}},
            upsert=True,
        )

        embed = await self.get_all_bansettings(ctx, key=5)
        return await ctx.send_followup(
            content=f"{self.client.yes} Custom emoji successfully updated to [ {emoji} ]",
            embed=embed,
        )

    async def selfbanchance(self, ctx: ApplicationContext, percentage: int = None):
        if not percentage:
            try:
                await self.client.self_ban_chance.delete_one({"_id": ctx.guild.id})
            except Exception:
                pass
            embed = await self.get_all_bansettings(ctx, key=6)
            await ctx.send_followup(
                content=f"{self.client.yes} Self-ban chance successfully reset",
                embed=embed,
            )
            return

        await self.client.self_ban_chance.update_one(
            {"_id": ctx.guild.id},
            {"$set": {"_id": ctx.guild.id, "percentage": percentage}},
            upsert=True,
        )

        embed = await self.get_all_bansettings(ctx, key=6)
        await ctx.send_followup(
            content=f"{self.client.yes} Self-ban chance successfully updated to `{percentage}%`",
            embed=embed,
        )
        return

    async def bandm(self, ctx: ApplicationContext, message: str = None):
        if not message:
            try:
                await self.client.ban_dm.delete_one({"_id": ctx.guild.id})
            except Exception:
                pass
            embed = await self.get_all_bansettings(ctx, key=7)
            await ctx.send_followup(
                content=f"{self.client.yes} Ban DM successfully reset", embed=embed
            )
            return

        shortened = message[:]
        if len(message) > 25:
            shortened = message[:25] + "..."
        await self.client.ban_dm.update_one(
            {"_id": ctx.guild.id},
            {
                "$set": {
                    "_id": ctx.guild.id,
                    "message": message,
                    "shortened": shortened,
                }
            },
            upsert=True,
        )

        embed = await self.get_all_bansettings(ctx, key=7)
        await ctx.send_followup(
            content=f"{self.client.yes} Ban DM successfully updated to ```fix\n{message}\n```",
            embed=embed,
        )
        return

    async def selfbandm(self, ctx: ApplicationContext, message: str = None):
        if not message:
            try:
                await self.client.self_ban_dm.delete_one({"_id": ctx.guild.id})
            except Exception:
                pass
            embed = await self.get_all_bansettings(ctx, key=8)
            await ctx.send_followup(
                content=f"{self.client.yes} Self-ban DM successfully reset", embed=embed
            )
            return

        shortened = message[:]
        if len(message) > 25:
            shortened = message[:25] + "..."
        await self.client.self_ban_dm.update_one(
            {"_id": ctx.guild.id},
            {
                "$set": {
                    "_id": ctx.guild.id,
                    "message": message,
                    "shortened": shortened,
                }
            },
            upsert=True,
        )

        embed = await self.get_all_bansettings(ctx, key=8)
        await ctx.send_followup(
            content=f"{self.client.yes} Self-ban DM successfully updated to ```fix\n{message}\n```",
            embed=embed,
        )
        return

    async def clear(self, ctx: ApplicationContext):
        dickt = {"yes_or_no": "no"}
        gS = await self.client.starter.find_one({"_id": ctx.guild.id})
        tTJ = await self.client.time_to_join.find_one({"_id": ctx.guild.id})
        gT = await self.client.game_timeout.find_one({"_id": ctx.guild.id})
        plR = await self.client.ban_gamer.find_one({"_id": ctx.guild.id})
        cE = await self.client.game_emoji.find_one({"_id": ctx.guild.id})
        sBC = await self.client.self_ban_chance.find_one({"_id": ctx.guild.id})
        bD = await self.client.ban_dm.find_one({"_id": ctx.guild.id})
        sBD = await self.client.self_ban_dm.find_one({"_id": ctx.guild.id})
        if gS:
            await self.client.starter.delete_one({"_id": ctx.guild.id})
            dickt["yes_or_no"] = "yes"
        if tTJ:
            await self.client.time_to_join.delete_one({"_id": ctx.guild.id})
            dickt["yes_or_no"] = "yes"
        if gT:
            await self.client.game_timeout.delete_one({"_id": ctx.guild.id})
            dickt["yes_or_no"] = "yes"
        if plR:
            await self.client.ban_gamer.delete_one({"_id": ctx.guild.id})
            dickt["yes_or_no"] = "yes"
        if cE:
            await self.client.game_emoji.delete_one({"_id": ctx.guild.id})
            dickt["yes_or_no"] = "yes"
        if sBC:
            await self.client.self_ban_chance.delete_one({"_id": ctx.guild.id})
            dickt["yes_or_no"] = "yes"
        if bD:
            await self.client.ban_dm.delete_one({"_id": ctx.guild.id})
            dickt["yes_or_no"] = "yes"
        if sBD:
            await self.client.self_ban_dm.delete_one({"_id": ctx.guild.id})
            dickt["yes_or_no"] = "yes"
        if dickt["yes_or_no"] == "yes":
            await ctx.defer()
            embed = await self.get_all_bansettings(ctx, key=100)
            return await ctx.send_followup(
                content=f"{self.client.yes} This server's game configurations have been cleared",
                embed=embed,
            )

        return await ctx.send_response("No configurations are set yet", ephemeral=True)

    @start.error
    async def start_error(
        self,
        ctx: ApplicationContext,
        error: discord.commands.ApplicationCommandInvokeError,
    ):
        if hasattr(error, "original"):
            error = error.original

        if isinstance(error, commands.BotMissingPermissions):
            embed = discord.Embed(
                title="Yeah, so uhhh",
                description=f"{error}\n[`/game explain`] for more info",
                color=Botcolours.red,
            )
            ctx.command.reset_cooldown(ctx)
            return await ctx.respond(embed=embed, ephemeral=True)
        if isinstance(error, commands.MissingPermissions):
            errorEmbed = discord.Embed(
                title="Yeah, so uhhh",
                description=f"You need the set Game Starter role [`/bansettings`] or `Manage Server` permissions to use this command!",
                color=Botcolours.red,
            )
            ctx.command.reset_cooldown(ctx)
            return await ctx.respond(embed=errorEmbed, ephemeral=True)

    @bansettings.error
    async def bansettings_error(
        self,
        ctx: ApplicationContext,
        error: discord.commands.ApplicationCommandInvokeError,
    ):
        if hasattr(error, "original"):
            if isinstance(error.original, commands.MissingPermissions):
                embed = discord.Embed(
                    title="Yeah, so uhhh",
                    description=f"You need Manage Server permissions to perform these actions!",
                    color=Botcolours.red,
                )
                return await ctx.send_response(embed=embed, ephemeral=True)


def setup(client: BanBattler):
    client.add_cog(BanBattle(client=client))
