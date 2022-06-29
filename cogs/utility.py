import random
import time
from datetime import datetime

import discord
from discord import Interaction
from discord.app_commands import command, context_menu, describe
from discord.ext import commands

from bot import NotGDKID
from config.utils import Confirm


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
            takeaway = random.choices(population=[1, 2], weights=(70, 30), k=20)[
                random.randint(0, 19)
            ]
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

        again: bool = random.choices(population=[True, False], weights=(20, 80), k=20)[
            random.randint(0, 19)
        ]

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


class InviteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        bot = discord.ui.Button(
            label="invite me",
            style=discord.ButtonStyle.link,
            url="https://discord.com/api/oauth2/authorize?client_id=859104775429947432&permissions=412384484416&scope=bot%20applications.commands",
        )
        support = discord.ui.Button(
            label="get support",
            style=discord.ButtonStyle.link,
            url="https://discord.gg/DzN4U8veab",
        )

        self.add_item(bot)
        self.add_item(support)

        self.stop()


@context_menu(name="Invite Bot")
async def invite_bot(interaction: Interaction, member: discord.Member):
    if not member.bot:
        return await interaction.response.send_message(
            f"{member.mention} is not a bot", ephemeral=True
        )

    url = f"https://discord.com/oauth2/authorize?client_id={member.id}&permissions=543312838143&scope=bot%20applications.commands"

    return await interaction.response.send_message(
        f"[click here to invite {member.name}]({url}) (feel free to toggle the invite's permissions as needed)",
        ephemeral=True,
    )


class Utility(commands.Cog):
    def __init__(self, client: NotGDKID):
        self.client = client

        self.client.tree.add_command(invite_bot)

    @commands.Cog.listener()
    async def on_ready(self):
        print("Utility cog loaded")

    @command(name="markdown")
    @describe(text="the text you want to nuke")
    async def markdown(self, interaction: Interaction, text: str):
        """nuke some text"""
        output = markdownify(text)

        try:
            await interaction.response.send_message(
                f"```{output}```\n**copy paste the stuff above into the chat or smth**",
                ephemeral=True,
            )

        except discord.HTTPException:
            await interaction.response.send_message(
                "something went wrong, most likely the output exceeded my character limit in sending messages",
                ephemeral=True,
            )

    @command(name="ping")
    async def ping(self, interaction: Interaction):
        """latency"""

        receival = round(
            (datetime.now().timestamp() - interaction.created_at.timestamp()) * 1000, 2
        )

        start = time.monotonic()
        await self.client.db.execute("SELECT 1")
        database = round((time.monotonic() - start) * 1000, 2)

        websocket = round(self.client.latency * 1000, 2)

        embed = discord.Embed(
            description="\n".join(
                [
                    "```yaml\n",
                    f"receival  : {receival}ms",
                    f"websocket : {websocket}ms",
                    f"database  : {database}ms",
                    "```",
                ]
            )
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @command(name="invite")
    async def invite(self, interaction: Interaction):
        """invite the bot"""
        await interaction.response.send_message(view=InviteView(), ephemeral=True)

    @command(name="forgetmydata")
    async def forgetmydata(self, interaction: Interaction):
        """clears out any data i have stored on you"""

        view = Confirm(interaction.user)
        confirm_embed = discord.Embed(
            title="confirm data delete?",
            description="this will delete all of your saved games / saved configurations",
            colour=0x09DFFF,
        )

        await interaction.response.send_message(
            embed=confirm_embed, view=view, ephemeral=True
        )
        setattr(view, "original_message", await interaction.original_message())

        await view.wait()

        if view.choice is True:
            await view.interaction.response.edit_message(view=view)
            await view.interaction.followup.send("data cleared", ephemeral=True)

            query = """SELECT tablename FROM pg_tables
                        WHERE tableowner = 'GDKID'
                    """
            data = await self.client.db.fetch(query)

            for record in data:
                tablename = record[0]

                query = "DELETE FROM %s WHERE user_id = $1" % tablename
                await self.client.db.execute(query, interaction.user.id)

        else:
            await view.interaction.response.edit_message(view=view)
            await view.interaction.followup.send("k nvm then", ephemeral=True)


async def setup(client: commands.Bot):
    await client.add_cog(Utility(client))
