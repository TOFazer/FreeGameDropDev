"""Faux serveur Discord : les tests tournent sans token ni connexion réseau.

Les objets ci-dessous imitent juste ce que le bot utilise réellement
(`guild.create_role`, `channel.edit`, `category.text_channels`...), ce qui suffit
à rejouer un `/setup-auto` complet en mémoire.
"""

from types import SimpleNamespace

import discord
import pytest

import database
from cogs.jeux import Jeux
from services import epic_games


@pytest.fixture(autouse=True)
def _no_real_epic_calls(request, monkeypatch):
    """Aucun test ne doit déclencher un vrai appel réseau vers l'Epic Games Store.

    `tests/test_epic_games.py` teste `fetch_giveaways` lui-même et gère déjà
    ses propres doubles de test : il est exclu de ce garde-fou.
    """
    if "test_epic_games" in request.node.nodeid:
        return

    async def _empty():
        return []

    monkeypatch.setattr(epic_games, "fetch_giveaways", _empty)


class FakeRole:
    def __init__(self, name, role_id, default=False):
        self.name = name
        self.id = role_id
        self.colour = None
        self.mentionable = False
        self.deleted = False
        self._default = default

    def is_default(self):
        return self._default

    @property
    def mention(self):
        return f"<@&{self.id}>"

    async def edit(self, **kwargs):
        kwargs.pop("reason", None)
        self.__dict__.update(kwargs)

    async def delete(self, reason=None):
        self.deleted = True

    def __repr__(self):
        return f"<FakeRole {self.name}>"


class FakeMember:
    def __init__(self, member_id, permissions=None, name="BOT"):
        self.id = member_id
        self.name = name
        self.guild_permissions = permissions or discord.Permissions.all()


class FakeMessage:
    def __init__(self, channel, author_id, guild):
        self.channel = channel
        self.guild = guild
        self.author = FakeMember(author_id)
        self.deleted = False

    async def delete(self):
        self.deleted = True


class FakeSentMessage:
    def __init__(self, channel, message_id, payload):
        self.channel = channel
        self.id = message_id
        self.payload = payload
        self.author = channel.guild.me
        self.deleted = False

    async def edit(self, **kwargs):
        if self.deleted:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "Unknown Message")
        self.payload.update(kwargs)

    async def delete(self):
        self.deleted = True


class FakePartialMessage:
    def __init__(self, channel, message_id):
        self.channel = channel
        self.message_id = message_id

    async def edit(self, **kwargs):
        message = next(
            (m for m in self.channel.messages if m.id == self.message_id and not m.deleted), None
        )
        if message is None:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "Unknown Message")
        await message.edit(**kwargs)


class FakeChannel:
    def __init__(self, name, category, overwrites=None, topic=None, channel_id=None):
        self.name = name
        self.category = category
        self.guild = category.guild if category else None
        self.overwrites = overwrites or {}
        self.topic = topic
        self.id = channel_id if channel_id is not None else next(_ids)
        self.sent = []
        self.moved = False
        self.deleted = False
        self.messages = []

    @property
    def mention(self):
        return f"<#{self.name}>"

    async def edit(self, **kwargs):
        previous_category = self.category
        if "category" in kwargs and previous_category and self in previous_category.channels:
            previous_category.channels.remove(self)
        self.__dict__.update(kwargs)
        if "category" in kwargs and kwargs["category"] is not None:
            self.category = kwargs["category"]
            if self not in self.category.channels:
                self.category.channels.append(self)
        elif "category" in kwargs:
            self.category = None

    async def move(self, **kwargs):
        self.moved = True

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        message = FakeSentMessage(self, next(_ids), kwargs)
        self.messages.append(message)
        return message

    def get_partial_message(self, message_id):
        return FakePartialMessage(self, message_id)

    def history(self, limit=50):
        messages = list(self.messages)[:limit]

        async def iterator():
            for message in messages:
                yield message

        return iterator()

    async def delete(self, reason=None):
        self.deleted = True
        if self.category and self in self.category.channels:
            self.category.channels.remove(self)


class FakeCategory:
    def __init__(self, guild, name, overwrites=None):
        self.guild = guild
        self.name = name
        self.overwrites = overwrites or {}
        self.channels = []
        self.deleted = False

    @property
    def text_channels(self):
        return list(self.channels)

    async def create_text_channel(self, name, topic=None, overwrites=None):
        channel = FakeChannel(name, self, overwrites, topic)
        self.channels.append(channel)
        return channel

    async def delete(self, reason=None):
        self.deleted = True
        if self in self.guild.categories:
            self.guild.categories.remove(self)


def _id_generator():
    current = 1000
    while True:
        current += 1
        yield current


_ids = _id_generator()


class FakeGuild:
    def __init__(self, permissions=None, guild_id=7):
        self.id = guild_id
        self.default_role = FakeRole("@everyone", 1, default=True)
        self.me = FakeMember(999, permissions)
        self.roles = [self.default_role]
        self.categories = []

    def get_role(self, role_id):
        return next((r for r in self.roles if r.id == role_id and not r.deleted), None)

    def get_channel(self, channel_id):
        for category in self.categories:
            for channel in category.channels:
                if channel.id == channel_id:
                    return channel
        return None

    @property
    def text_channels(self):
        return [channel for category in self.categories for channel in category.text_channels]

    def add_role(self, name):
        role = FakeRole(name, next(_ids))
        self.roles.append(role)
        return role

    async def create_role(self, name, colour=None, mentionable=False, reason=None):
        role = FakeRole(name, next(_ids))
        role.colour = colour
        role.mentionable = mentionable
        self.roles.append(role)
        return role

    async def create_category(self, name, overwrites=None):
        category = FakeCategory(self, name, overwrites)
        self.categories.append(category)
        return category


class FakeBot:
    def __init__(self, guild=None):
        self.user = FakeMember(999)
        self.guild = guild

    def get_channel(self, channel_id):
        return self.guild.get_channel(channel_id) if self.guild else None


@pytest.fixture
def fakes():
    """Les classes ci-dessus, pour que les tests n'aient rien à importer d'ici.

    (Un `from tests.conftest import ...` créerait une seconde copie du module.)
    """
    return SimpleNamespace(
        Guild=FakeGuild,
        Role=FakeRole,
        Member=FakeMember,
        Message=FakeMessage,
        Channel=FakeChannel,
        Category=FakeCategory,
        Bot=FakeBot,
    )


@pytest.fixture
def guild():
    return FakeGuild()


@pytest.fixture
def bot(guild):
    return FakeBot(guild)


def build_cog(guild):
    """Le cog sans sa boucle de vérification (qui exigerait une vraie connexion)."""
    instance = Jeux.__new__(Jeux)
    instance.bot = FakeBot(guild)
    instance.roles_channels = {}
    return instance


@pytest.fixture
def cog(guild):
    return build_cog(guild)


@pytest.fixture
def cog_for():
    """Pour les tests qui ont besoin d'un serveur particulier (bot bridé, etc.)."""
    return build_cog


@pytest.fixture
async def db(tmp_path, monkeypatch):
    """Base SQLite jetable, propre à chaque test."""
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    await database.init_db()
    return database
