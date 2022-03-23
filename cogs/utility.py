import random
from random import choice as c

import discord
from discord.commands import (ApplicationContext, Option, slash_command,
                              user_command)
from discord.ext import commands

from bot import NotGDKID
from config.utils import CHOICES


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


class ClearConfirm(discord.ui.View):
    def __init__(self, owner_id: int):
        self.choice = False
        self.owner_id = owner_id
        self.original_message = None

        super().__init__(timeout=120)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(content=c(CHOICES), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for c in self.children:
            c.disabled = True

        await self.original_message.edit(view=self)
        self.stop()

    @discord.ui.button(label="ye")
    async def ye(self, btn: discord.ui.Button, interaction: discord.Interaction):
        for c in self.children:
            c.disabled = True

        btn.style = discord.ButtonStyle.success
        self.choice = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("data cleared", ephemeral=True)
        return self.stop()

    @discord.ui.button(label="nu")
    async def nu(self, btn: discord.ui.Button, interaction: discord.Interaction):
        for c in self.children:
            c.disabled = True

        btn.style = discord.ButtonStyle.success
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("k nvm then", ephemeral=True)
        return self.stop()


class InviteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        bot = discord.ui.Button(
            label="invite me",
            style=discord.ButtonStyle.link,
            url="https://discord.com/api/oauth2/authorize?client_id=859104775429947432&permissions=412384484416&scope=bot%20applications.commands",
        )
        support = discord.ui.Button(
            label="get support", style=discord.ButtonStyle.link, url="https://discord.gg/85sdd3EEMv"
        )

        self.add_item(bot)
        self.add_item(support)

        self.stop()


class Utility(commands.Cog):
    def __init__(self, client: NotGDKID):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print("Utility cog loaded")

    @user_command(name="Invite Bot")
    async def invite_bot(self, ctx: ApplicationContext, member: discord.Member):
        if not member.bot:
            return await ctx.respond(f"{member.mention} is not a bot", ephemeral=True)

        url = f"https://discord.com/oauth2/authorize?client_id={member.id}&permissions=543312838143&scope=bot%20applications.commands"

        return await ctx.respond(
            f"[click here to invite {member.name}]({url}) (feel free to toggle the invite's permissions as needed)",
            ephemeral=True,
        )

    @slash_command(name="markdown")
    async def markdown(self, ctx: ApplicationContext, text: Option(str, "the text you want to nuke", required=True)):
        """nuke some text"""
        output = markdownify(text)

        try:
            await ctx.respond(f"```{output}```\n**copy paste the stuff above into the chat or smth**", ephemeral=True)

        except discord.HTTPException:
            await ctx.respond(
                "something went wrong, most likely the output exceeded my character limit in sending messages",
                ephemeral=True,
            )

    @slash_command(name="ping")
    async def ping(self, ctx: ApplicationContext):
        """latency"""
        await ctx.respond(f"`{round(self.client.latency * 1000, 2)}ms`", ephemeral=True)

    @slash_command(name="invite")
    async def invite(self, ctx: ApplicationContext):
        """invite the bot"""
        await ctx.respond(view=InviteView(), ephemeral=True)

    @slash_command(name="forgetmydata")
    async def forgetmydata(self, ctx: ApplicationContext):
        """clears out any data i have stored on you"""

        view = ClearConfirm(ctx.author.id)
        confirm_embed = discord.Embed(
            title="confirm data delete?",
            description="this will delete all of your saved games / saved configurations",
            colour=0x09DFFF,
        )

        message = await ctx.respond(embed=confirm_embed, view=view, ephemeral=True)
        setattr(view, "original_message", await message.original_message())

        await view.wait()

        if view.choice is True:
            for i in self.client.cache.values():
                for item in i:
                    if ctx.author.id in item.values():
                        i.pop(i.index(item))

            for g in self.client.games:
                if g.game.player.id == ctx.author.id:
                    self.client.games.pop(self.client.games.index(g))
                    g.stop(save=False)
                    for c in g.children:
                        c.disabled = True

                    await ctx.interaction.followup.edit_message(message_id=g.original_message.id, view=g)


def setup(client: commands.Bot):
    client.add_cog(Utility(client))
