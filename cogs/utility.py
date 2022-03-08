import random

import discord
from discord.commands import (ApplicationContext, Option, slash_command,
                              user_command)
from discord.ext import commands


class Actions:
    @staticmethod
    def bold(arg: str):
        return "**" + arg + "**"

    @staticmethod
    def italics(arg: str):
        return "*" + arg + "*"

    @staticmethod
    def strikethrough(arg: str):
        return "~~" + arg + "~~"

    @staticmethod
    def underline(arg: str):
        return "__" + arg + "__"

    @staticmethod
    def codeblockify(arg: str):
        return "`" + arg + "`"

    @staticmethod
    def shuffle(arg: str):
        groups: dict[int, str] = {}

        counter = 0
        while arg != "":
            takeaway = random.choices(population=[1, 2], weights=(70, 30), k=20)[random.randint(0, 19)]
            groups[counter] = arg[:takeaway]
            arg = arg[takeaway:]
            counter += 1

        return list(groups.values())


def markdownify(string: str):
    group_list = Actions.shuffle(string)

    actions_list = [
        Actions.bold,
        Actions.italics,
        Actions.strikethrough,
        Actions.underline,
    ]
    popped_action = None

    for group in group_list:
        code: bool = random.choices(
            population=[True, False],
            weights=(40, 60),
            k=20,
        )[random.randint(0, 19)]

        if code:
            group_list[group_list.index(group)] = group = Actions.codeblockify(group)

        action = random.choice(actions_list)

        group_list[group_list.index(group)] = group = action(group)

        if popped_action:
            actions_list.append(popped_action)

        popped_action = actions_list.pop(actions_list.index(action))

        again: bool = random.choices(population=[True, False], weights=(20, 80), k=20)[random.randint(0, 19)]

        if again:
            action = random.choice(actions_list)

            group_list[group_list.index(group)] = group = action(group)

            if popped_action:
                actions_list.append(popped_action)

            popped_action = actions_list.pop(actions_list.index(action))

    string = "\u200b".join(group_list)

    string = string.replace("b", "🅱️")
    string = string.replace("B", "🅱️")
    string = string.replace("`\:b:`", "🅱️")
    string = string.replace("` \:b:`", "🅱️")
    string = string.replace(" * ", "* ")

    return string


class Utility(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print("Utility cog loaded")

    @user_command(name="Invite Bot")
    async def invite_bot(self, ctx: ApplicationContext, member: discord.Member):
        if not member.bot:
            return await ctx.respond(f"{member.mention} is not a bot", ephemeral=True)

        url = f"https://discord.com/oauth2/authorize?client_id={member.id}&permissions=1099511627775&scope=bot%20applications.commands"

        return await ctx.respond(
            f"[Click here to invite {member.name}]({url}) (feel free to toggle the invite's permissions as needed)",
            ephemeral=True,
        )

    @slash_command(name="markdown")
    async def markdown(self, ctx: ApplicationContext, text: Option(str, "the text you want to nuke", required=True)):
        """make you look high or smth idk (works best on desktop)"""
        output = markdownify(text)

        try:
            await ctx.respond(f"```{output}```\n**Copy paste the stuff in the codeblock above**", ephemeral=True)

        except discord.HTTPException:
            await ctx.respond(
                "Something went wrong, most likely the output exceeded my character limit in sending messages or smth like that",
                ephemeral=True,
            )


def setup(client: commands.Bot):
    client.add_cog(Utility(client))
