import random
from typing import *

import discord
from discord.ext import commands
from discord.ext.commands import Cog, Command, Group

from bot import BanBattler
from config.utils import BattlerCog, Botcolours

commands_module = commands  # This word clashes a lot throughout the subclass


class HelpCommand(commands.HelpCommand):

    """Our very smegc help command"""

    def __init__(self):

        super().__init__(
            verify_checks=False,
            command_attrs={
                "name": "help",
                "brief": "Gives help on the bot",
                "aliases": ["commands", "cmd", "h"],
                "cooldown": commands.CooldownMapping.from_cooldown(
                    1, 3, commands.BucketType.user
                ),
            },
        )
        self.context: commands.Context = self.context

    def get_command_signature(
        self, command: Union[Command, Group], with_prefix: bool = False
    ):
        """Gets the signature of a command. You can specify wether you want the prefix to be included in the result or not"""
        return f'{self.context.clean_prefix if with_prefix else ""}{command.qualified_name} {command.signature}** ***'

    def alias(self, command: Union[Command, Group]):
        """Gets the aliases of a command"""
        if command.aliases != [] or None:
            return "\n*Aliases: {0}*".format(", ".join(command.aliases))
        else:
            return " ** **"

    def description(self, command: Union[Command, Group]):
        """Gets the description of a command"""
        if command.description != None and "e" in command.description.lower():
            return "\n\n{0}".format(command.description)
        else:
            return " ** **"

    def more_help(self, command: Union[Command, Group]):
        """Gets the help of a command"""
        if command.help != None:
            return "\n\n{0}".format(command.help)
        else:
            return " ** **"

    async def subcommands(self, command_list: list[Command]) -> str:
        """Gets the subcommands a of group"""
        L = []
        for command in command_list:
            try:
                await command.can_run(self.context)
            except Exception:
                continue
            else:
                L.append(
                    "`{0.name}: ` {1}\n*Command usage: {2}".format(
                        command,
                        self.brief_or_help(command),
                        self.get_command_signature(command, with_prefix=True),
                    )
                )
        return "\n\n".join(L)

    def cooldown(self, command: Union[Command, Group]):
        """Gets the cooldown of a command"""
        try:
            cooldown_bucket = command._buckets.get_bucket(self.context.message)
            return ["Cooldown", round(cooldown_bucket.rate), round(cooldown_bucket.per)]
        except AttributeError:
            return " ** **"

    def max_concurrency(self, command: Union[Command, Group]):
        """Gets the max concurrency of a command"""
        try:
            concurrency_bucket = command._max_concurrency
            return [
                "Maximum concurrency",
                concurrency_bucket.number,
                str(concurrency_bucket.per)[11:],
            ]
        except AttributeError:
            return " ** **"

    def brief_or_help(self, command: Union[Command, Group]):
        """Returns either the brief or the help of a command based on whats available"""

        if command.brief is not None:
            return command.brief
        list_thing = [
            "Does stuff",
            "Has functionality",
            "Somewhat works",
            "Runs part of my code",
            "Surprisingly functional",
            "Working code",
            "Serves use",
        ]
        return random.choice(list_thing)

    async def send_bot_help(self, mapping: Mapping[BattlerCog, Iterable[Command]]):
        embed = discord.Embed(
            description="__Command categories:__", color=Botcolours.cyan
        )
        embed.set_author(
            name="Help Menu",
            icon_url=self.context.bot.user.avatar,
        )
        embed.set_footer(
            text="{0}help <category> for more info".format(self.context.clean_prefix)
        )
        for cog, commands in mapping.items():
            filtered = await self.filter_commands(commands, sort=True)
            if filtered:
                if cog == None:
                    continue
                cog_name: str = cog.qualified_name
                cog_name: str = cog_name[0].upper() + cog_name[1:]
                if cog_name != "No Category":
                    try:
                        cog_emoji = cog.emoji
                    except AttributeError:
                        cog_emoji = ""
                    all_commands: list[Union[Group, Command]] = list(
                        cog.walk_commands()
                    )
                    counter: int = 0
                    for command in all_commands:
                        try:
                            await command.can_run(self.context)
                        except Exception:
                            continue
                        else:
                            counter += 1
                    embed.add_field(
                        name="{0} {1}".format(cog_emoji, cog_name),
                        value="*{0.description}*\n`{1} total`".format(cog, counter),
                        inline=False,
                    )

        await self.context.reply(embed=embed)

    async def send_cog_help(self, cog: Cog):
        cog_name: str = cog.qualified_name[0].capitalize() + cog.qualified_name[1:]
        if cog_name.lower() == "help":
            await self.send_command_help(self.context.command)
            return
        embed = discord.Embed(
            description="**__{0} commands:__**".format(cog_name),
            color=Botcolours.cyan,
        )
        embed.set_author(
            name="Help Menu",
            icon_url=self.context.bot.user.avatar,
        )
        embed.set_footer(
            text="{0}help <command> for more info".format(self.context.clean_prefix)
        )
        commands: list[Union[Group, Command]] = cog.get_commands()
        await self.filter_commands(commands, sort=True)
        for command in commands:
            command: Union[Group, Command] = command
            try:
                await command.can_run(self.context)
            except Exception:
                continue
            else:
                command_signature = self.get_command_signature(
                    command, with_prefix=True
                )
                if not command.hidden:
                    a_list = []
                    if isinstance(command, Group):
                        for c in command.commands:
                            try:
                                await c.can_run(self.context)
                            except commands_module.CommandError:
                                continue
                            else:
                                a_list.append(c)

                    embed.description = (
                        embed.description
                        + "\n\n`{0.qualified_name}: ` {1}\n*Command usage: {2}{3}{4}".format(
                            command,
                            command.short_doc
                            if isinstance(command, Group)
                            else self.brief_or_help(command),
                            command_signature,
                            self.alias(command),
                            "\n*`" + str(len(a_list)) + " subcommands`*"
                            if isinstance(command, Group) and len(a_list) > 0
                            else "",
                        )
                    )

        await self.context.reply(embed=embed)

    async def send_group_help(self, group: Group):
        subcommands = list(group.walk_commands())
        list_subcommands = await self.subcommands(subcommands)
        await self.filter_commands(subcommands, sort=True)
        embed = discord.Embed(
            description="`{0.qualified_name}: ` {0.brief}\n*Command usage: {1}{2}{3}{4}{5}".format(
                group,
                self.get_command_signature(group, with_prefix=True),
                self.alias(group),
                "\n\n**Subcommands**\n" if list_subcommands != "" else "",
                list_subcommands,
                self.more_help(group),
            ),
            color=Botcolours.cyan,
        )
        thing = self.cooldown(group)
        if type(thing) == list:
            embed.add_field(
                name=thing[0],
                value=f"{thing[1]} use(s) per {thing[2]} seconds",
                inline=False,
            )
        embed.set_author(
            name="Help Menu",
            icon_url=self.context.bot.user.avatar,
        )
        embed.set_footer(
            text="{0}help {1} <subcommand> for more info".format(
                self.context.clean_prefix, group
            )
        )

        await self.context.reply(embed=embed)

    async def send_command_help(self, command: Command):
        command_signature = self.get_command_signature(command, with_prefix=True)
        embed = discord.Embed(
            description="`{0.qualified_name}: ` {1}\n*Command usage: {2}{3}{4}{5}".format(
                command,
                self.brief_or_help(command),
                command_signature,
                self.alias(command),
                self.description(command),
                self.more_help(command),
            ),
            color=Botcolours.cyan,
        )
        thing = self.max_concurrency(command)
        thing2 = self.cooldown(command)
        if type(thing) == list:
            embed.add_field(
                name=thing[0], value=f"{thing[1]} use(s) per {thing[2]}", inline=False
            )
        if type(thing2) == list:
            embed.add_field(
                name=thing2[0],
                value=f"{thing2[1]} use(s) per {thing2[2]} seconds",
                inline=False,
            )
        embed.set_author(
            name="Help Menu",
            icon_url=self.context.bot.user.avatar,
        )
        embed.set_footer(
            text="Arguments in <> are required | [] are optional\n[p] represents your prefix"
        )

        await self.context.reply(embed=embed)

    async def send_error_message(self, error):
        mapping: Mapping[BattlerCog, Iterable[Command]] = self.get_bot_mapping()
        await self.send_bot_help(mapping=mapping)
        del error

    async def command_callback(self, ctx: commands.Context, *, command: str = None):
        command = command.lower() if command is not None else ""

        await self.prepare_help_command(ctx, command)

        bot: BanBattler = ctx.bot

        if command is None:
            mapping = self.get_bot_mapping()
            return await self.send_bot_help(mapping)

        cogs_lower = {k.lower(): v for k, v in bot.cogs.items()}
        try:
            return await self.send_cog_help(cogs_lower[command])

        except KeyError:
            pass

        maybe_coro = discord.utils.maybe_coroutine
        keys = command.split(" ")
        cmd = bot.all_commands.get(keys[0])

        if cmd is None:
            string = await maybe_coro(
                self.command_not_found, self.remove_mentions(keys[0])
            )
            return await self.send_error_message(string)

        for key in keys[1:]:
            try:
                found = cmd.all_commands.get(key)
            except AttributeError:
                string = await maybe_coro(
                    self.subcommand_not_found, cmd, self.remove_mentions(key)
                )
                return await self.send_error_message(string)
            else:
                if found is None:
                    string = await maybe_coro(
                        self.subcommand_not_found, cmd, self.remove_mentions(key)
                    )
                    return await self.send_error_message(string)
                cmd = found

        if isinstance(cmd, Group):
            return await self.send_group_help(cmd)
        else:
            return await self.send_command_help(cmd)


class help(BattlerCog):
    def __init__(self, client: BanBattler):
        self.description = "Gives help on the bot"
        self.client = client
        self._original_help_command = client.help_command
        self.emoji = "<a:question:848014941298098226>"
        client.help_command = HelpCommand()
        client.help_command.cog = self

    def cog_unload(self):
        self.client.help_command = self._original_help_command

    @BattlerCog.listener()
    async def on_ready(self):
        print("Help cog loaded")


def setup(client: BanBattler):
    client.add_cog(help(client=client))
