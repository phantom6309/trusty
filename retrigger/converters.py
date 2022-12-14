import asyncio
import logging
from typing import List, Pattern, Tuple, Union, Optional, Literal

import discord
from discord.ext.commands.converter import Converter, IDConverter, RoleConverter
from discord.ext.commands.errors import BadArgument
from redbot import VersionInfo, version_info
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

log = logging.getLogger("red.trusty-cogs.ReTrigger")
_ = Translator("ReTrigger", __file__)

try:
    import regex as re
except ImportError:
    import re


class MultiResponse(Converter):
    """
    This will parse my defined multi response pattern and provide usable formats
    to be used in multiple reponses
    """

    async def convert(self, ctx: commands.Context, argument: str) -> Union[List[str], List[int]]:
        result = []
        match = re.split(r"(;)", argument)
        valid_reactions = [
            "dm",
            "dmme",
            "remove_role",
            "add_role",
            "ban",
            "kick",
            "text",
            "filter",
            "delete",
            "publish",
            "react",
            "rename",
            "command",
            "mock",
        ]
        log.debug(match)
        my_perms = ctx.channel.permissions_for(ctx.me)
        if match[0] not in valid_reactions:
            raise BadArgument(
                _("`{response}` is not a valid reaction type.").format(response=match[0])
            )
        for m in match:
            if m == ";":
                continue
            else:
                result.append(m)
        if result[0] == "filter":
            result[0] = "delete"
        if len(result) < 2 and result[0] not in ["delete", "ban", "kick"]:
            raise BadArgument(_("The provided multi response pattern is not valid."))
        if result[0] in ["add_role", "remove_role"] and not my_perms.manage_roles:
            raise BadArgument(_('I require "Manage Roles" permission to use that.'))
        if result[0] == "filter" and not my_perms.manage_messages:
            raise BadArgument(_('I require "Manage Messages" permission to use that.'))
        if result[0] == "publish" and not my_perms.manage_messages:
            raise BadArgument(_('I require "Manage Messages" permission to use that.'))
        if result[0] == "ban" and not my_perms.ban_members:
            raise BadArgument(_('I require "Ban Members" permission to use that.'))
        if result[0] == "kick" and not my_perms.kick_members:
            raise BadArgument(_('I require "Kick Members" permission to use that.'))
        if result[0] == "react" and not my_perms.add_reactions:
            raise BadArgument(_('I require "Add Reactions" permission to use that.'))
        if result[0] == "mock":
            msg = await ctx.send(
                _(
                    "Mock commands can allow any user to run a command "
                    "as if you did, are you sure you want to add this?"
                )
            )
            start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(msg, ctx.author)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=15)
            except asyncio.TimeoutError:
                raise BadArgument(_("Not creating trigger."))
            if not pred.result:
                raise BadArgument(_("Not creating trigger."))

        def author_perms(ctx: commands.Context, role: discord.Role) -> bool:
            if (
                ctx.author.id == ctx.guild.owner_id
            ):  # handles case where guild is not chunked and calls for the ID thru the endpoint instead
                return True
            return role < ctx.author.top_role

        if result[0] in ["add_role", "remove_role"]:
            good_roles = []
            for r in result[1:]:
                try:
                    role = await RoleConverter().convert(ctx, r)
                    if role < ctx.guild.me.top_role and author_perms(ctx, role):
                        good_roles.append(role.id)
                except BadArgument:
                    log.error("Role `{}` not found.".format(r))
            result = [result[0]]
            for r_id in good_roles:
                result.append(r_id)
        if result[0] == "react":
            good_emojis: List[Union[discord.Emoji, str]] = []
            for r in result[1:]:
                try:
                    emoji = await ValidEmoji().convert(ctx, r)
                    good_emojis.append(emoji)
                except BadArgument:
                    log.error("Emoji `{}` not found.".format(r))
            log.debug(good_emojis)
            result = [result[0]] + good_emojis
        return result


class Trigger:
    """
    Trigger class to handle trigger objects
    """

    name: str
    regex: Pattern
    response_type: List[
        Literal[
            "dm",
            "dmme",
            "remove_role",
            "add_role",
            "ban",
            "kick",
            "text",
            "delete",
            "publish",
            "react",
            "rename",
            "command",
            "mock",
        ]
    ]
    author: int
    count: int
    image: Union[List[Union[int, str]], str, None]
    text: Union[List[Union[int, str]], str, None]
    whitelist: list
    blacklist: list
    cooldown: dict
    multi_payload: Union[List[MultiResponse], Tuple[MultiResponse, ...]]
    created: int
    ignore_commands: bool
    check_edits: bool
    ocr_search: bool
    delete_after: int
    read_filenames: bool
    chance: int
    reply: Optional[bool]
    tts: bool
    user_mention: bool
    role_mention: bool
    everyone_mention: bool
    nsfw: bool

    def __init__(self, name, regex, response_type, author, **kwargs):
        self.name = name
        try:
            self.regex = re.compile(regex)
        except Exception:
            raise
        self.response_type = response_type
        self.author = author
        self.enabled = kwargs.get("enabled", True)
        self.count = kwargs.get("count", 0)
        self.image = kwargs.get("image", None)
        self.text = kwargs.get("text", None)
        self.whitelist = kwargs.get("whitelist", [])
        self.blacklist = kwargs.get("blacklist", [])
        self.cooldown = kwargs.get("cooldown", {})
        self.multi_payload = kwargs.get("multi_payload", [])
        self.created_at = kwargs.get("created_at", 0)
        self.ignore_commands = kwargs.get("ignore_commands", False)
        self.check_edits = kwargs.get("check_edits", False)
        self.ocr_search = kwargs.get("ocr_search", False)
        self.delete_after = kwargs.get("delete_after", None)
        self.read_filenames = kwargs.get("read_filenames", False)
        self.chance = kwargs.get("chance", 0)
        self.reply = kwargs.get("reply", None)
        self.tts = kwargs.get("tts", False)
        self.user_mention = kwargs.get("user_mention", True)
        self.role_mention = kwargs.get("role_mention", False)
        self.everyone_mention = kwargs.get("everyone_mention", False)
        self.nsfw = kwargs.get("nsfw", False)

    def enable(self):
        """Explicitly enable this trigger"""
        self.enabled = True

    def disable(self):
        """Explicitly disables this trigger"""
        self.enabled = False

    def toggle(self):
        """Toggle whether or not this trigger is enabled."""
        self.enabled = not self.enabled

    def allowed_mentions(self):
        if version_info >= VersionInfo.from_str("3.4.6"):
            return discord.AllowedMentions(
                everyone=self.everyone_mention,
                users=self.user_mention,
                roles=self.role_mention,
                replied_user=self.reply if self.reply is not None else False,
            )
        else:
            return discord.AllowedMentions(
                everyone=self.everyone_mention, users=self.user_mention, roles=self.role_mention
            )

    def __repr__(self):
        return "<ReTrigger name={0.name} author={0.author} response={0.response_type} pattern={0.regex.pattern}>".format(
            self
        )

    def __str__(self):
        """This is defined moreso for debugging purposes but may prove useful for elaborating
        what is defined for each trigger individually"""
        info = _(
            "__Name__: **{name}** \n"
            "__Active__: **{enabled}**\n"
            "__Author__: {author}\n"
            "__Count__: **{count}**\n"
            "__Response__: **{response}**\n"
        ).format(
            name=self.name,
            enabled=self.enabled,
            author=self.author,
            count=self.count,
            response=self.response_type,
        )
        return info

    async def to_json(self) -> dict:
        return {
            "name": self.name,
            "regex": self.regex.pattern,
            "response_type": self.response_type,
            "author": self.author,
            "enabled": self.enabled,
            "count": self.count,
            "image": self.image,
            "text": self.text,
            "whitelist": self.whitelist,
            "blacklist": self.blacklist,
            "cooldown": self.cooldown,
            "multi_payload": self.multi_payload,
            "created_at": self.created_at,
            "ignore_commands": self.ignore_commands,
            "check_edits": self.check_edits,
            "ocr_search": self.ocr_search,
            "delete_after": self.delete_after,
            "read_filenames": self.read_filenames,
            "chance": self.chance,
            "reply": self.reply,
            "tts": self.tts,
            "user_mention": self.user_mention,
            "everyone_mention": self.everyone_mention,
            "role_mention": self.role_mention,
            "nsfw": self.nsfw,
        }

    @classmethod
    async def from_json(cls, data: dict):
        # This should be used only for correcting improper types
        # All the defaults are handled in the class setup
        name = data.pop("name")
        regex = data.pop("regex")
        author = data.pop("author")
        response_type = data.pop("response_type", [])
        if isinstance(response_type, str):
            response_type = [data["response_type"]]
        if "delete" in response_type and isinstance(data["text"], bool):
            # replace old setting with new flag
            data["read_filenames"] = data["text"]
            data["text"] = None
        ignore_edits = data.get("ignore_edits", False)
        check_edits = data.get("check_edits")
        if check_edits is None and any(t in ["ban", "kick", "delete"] for t in response_type):
            data["check_edits"] = not ignore_edits
        return cls(name, regex, response_type, author, **data)


class TriggerExists(Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> Union[Trigger, str]:
        bot = ctx.bot
        guild = ctx.guild
        config = bot.get_cog("ReTrigger").config
        trigger_list = await config.guild(guild).trigger_list()
        result = None
        if argument in trigger_list:
            result = await Trigger.from_json(trigger_list[argument])
        else:
            result = argument
        return result


class ValidRegex(Converter):
    """
    This will check to see if the provided regex pattern is valid

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    """

    async def convert(self, ctx: commands.Context, argument: str) -> str:
        try:
            re.compile(argument)
            result = argument
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=argument, e=e)
            raise BadArgument(err_msg)
        return result


class ValidEmoji(IDConverter):
    """
    This is from discord.py rewrite, first we'll match the actual emoji
    then we'll match the emoji name if we can
    if all else fails we may suspect that it's a unicode emoji and check that later
    All lookups are done for the local guild first, if available. If that lookup
    fails, then it checks the client's global cache.
    The lookup strategy is as follows (in order):
    1. Lookup by ID.
    2. Lookup by extracting ID from the emoji.
    3. Lookup by name
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py
    """

    async def convert(self, ctx: commands.Context, argument: str) -> Union[discord.Emoji, str]:
        match = self._get_id_match(argument) or re.match(
            r"<a?:[a-zA-Z0-9\_]+:([0-9]+)>$|(:[a-zA-z0-9\_]+:$)", argument
        )
        result = None
        bot = ctx.bot
        guild = ctx.guild
        if match is None:
            # Try to get the emoji by name. Try local guild first.
            if guild:
                result = discord.utils.get(guild.emojis, name=argument)

            if result is None:
                result = discord.utils.get(bot.emojis, name=argument)
        elif match.group(1):
            emoji_id = int(match.group(1))

            # Try to look up emoji by id.
            if guild:
                result = discord.utils.get(guild.emojis, id=emoji_id)

            if result is None:
                result = discord.utils.get(bot.emojis, id=emoji_id)
        else:
            emoji_name = str(match.group(2)).replace(":", "")

            if guild:
                result = discord.utils.get(guild.emojis, name=emoji_name)

            if result is None:
                result = discord.utils.get(bot.emojis, name=emoji_name)
        if type(result) is discord.Emoji:
            result = str(result)[1:-1]

        if result is None:
            try:
                await ctx.message.add_reaction(argument)
                result = argument
            except Exception:
                raise BadArgument(_("`{}` is not an emoji I can use.").format(argument))

        return result


class ChannelUserRole(IDConverter):
    """
    This will check to see if the provided argument is a channel, user, or role

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    """

    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> Union[discord.TextChannel, discord.Member, discord.Role]:
        guild = ctx.guild
        result = None
        id_match = self._get_id_match(argument)
        channel_match = re.match(r"<#([0-9]+)>$", argument)
        member_match = re.match(r"<@!?([0-9]+)>$", argument)
        role_match = re.match(r"<@&([0-9]+)>$", argument)
        for converter in ["channel", "role", "member"]:
            if converter == "channel":
                match = id_match or channel_match
                if match:
                    channel_id = match.group(1)
                    result = guild.get_channel(int(channel_id))
                else:
                    result = discord.utils.get(guild.text_channels, name=argument)
            if converter == "member":
                match = id_match or member_match
                if match:
                    member_id = match.group(1)
                    result = guild.get_member(int(member_id))
                else:
                    result = guild.get_member_named(argument)
            if converter == "role":
                match = id_match or role_match
                if match:
                    role_id = match.group(1)
                    result = guild.get_role(int(role_id))
                else:
                    result = discord.utils.get(guild._roles.values(), name=argument)
            if result:
                break
        if not result:
            msg = _("{arg} is not a valid channel, user or role.").format(arg=argument)
            raise BadArgument(msg)
        return result
