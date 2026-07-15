import asyncio
import html
import random

import aiohttp
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

_rest: hikari.api.RESTClient | None = None

# Active trivia sessions: channel_id -> {question, answer, expires_at, message_id}
_trivia: dict[int, dict] = {}
# Active hangman sessions: channel_id -> {word, guessed, wrong, message_id, expires_at}
_hangman: dict[int, dict] = {}

HANGMAN_STAGES = [
    "```\n  +---+\n  |   |\n      |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n  |   |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|   |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n /    |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n / \\  |\n      |\n=========```",
]

WORDS = [
    "python", "discord", "lightbulb", "hikari", "server", "channel",
    "developer", "programming", "keyboard", "computer", "internet",
]


async def _expire_sessions() -> None:
    import time
    while True:
        await asyncio.sleep(30)
        now = asyncio.get_event_loop().time()
        for d in [_trivia, _hangman]:
            expired = [k for k, v in d.items() if v.get("expires_at", 0) < now]
            for k in expired:
                del d[k]


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest
    _rest = event.app.rest
    asyncio.create_task(_expire_sessions())
    logger.info("Games loaded.")


@loader.listener(hikari.GuildMessageCreateEvent)
async def on_message(event: hikari.GuildMessageCreateEvent) -> None:
    if event.author.is_bot or not event.content or _rest is None:
        return

    # Hangman guessing
    session = _hangman.get(event.channel_id)
    if session and len(event.content) == 1 and event.content.isalpha():
        letter = event.content.lower()
        if letter in session["guessed"]:
            return
        session["guessed"].add(letter)
        word = session["word"]

        if letter not in word:
            session["wrong"] += 1

        display = " ".join(c if c in session["guessed"] else "_" for c in word)
        wrong_count = session["wrong"]
        stage = HANGMAN_STAGES[min(wrong_count, len(HANGMAN_STAGES) - 1)]
        wrong_letters = ", ".join(sorted(c for c in session["guessed"] if c not in word)) or "*none*"

        if "_" not in display:
            del _hangman[event.channel_id]
            await _rest.create_message(event.channel_id, f"{stage}\n✅ You won! The word was **{word}**!")
        elif wrong_count >= len(HANGMAN_STAGES) - 1:
            del _hangman[event.channel_id]
            await _rest.create_message(event.channel_id, f"{stage}\n💀 Game over! The word was **{word}**.")
        else:
            await _rest.create_message(
                event.channel_id,
                f"{stage}\nWord: `{display}`\nWrong letters: {wrong_letters}\nWrong guesses: **{wrong_count}/6**"
            )


@loader.command
class Trivia(lightbulb.SlashCommand, name="trivia", description="Answer a trivia question."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if ctx.channel_id in _trivia:
            s = _trivia[ctx.channel_id]
            await ctx.respond(
                f"❓ A trivia question is already active in this channel!\n"
                f"**Question:** {s['question']}"
            )
            return

        async with aiohttp.ClientSession() as session:
            async with session.get("https://opentdb.com/api.php?amount=1&type=multiple") as resp:
                if resp.status != 200:
                    await ctx.respond("❌ Failed to fetch a trivia question.")
                    return
                data = await resp.json()

        if not data.get("results"):
            await ctx.respond("❌ No trivia question available right now.")
            return

        result = data["results"][0]
        question = html.unescape(result["question"])
        correct = html.unescape(result["correct_answer"])
        choices = [html.unescape(a) for a in result["incorrect_answers"]] + [correct]
        random.shuffle(choices)

        letters = ["A", "B", "C", "D"]
        options_text = "\n".join(f"**{letters[i]}.** {c}" for i, c in enumerate(choices))
        answer_letter = letters[choices.index(correct)]

        _trivia[ctx.channel_id] = {
            "question": question,
            "answer": answer_letter,
            "full_answer": correct,
            "expires_at": asyncio.get_event_loop().time() + 30,
        }

        await ctx.respond(
            f"❓ **Trivia Question:**\n{question}\n\n{options_text}\n\n*Reply with A, B, C, or D within 30 seconds!*"
        )

        await asyncio.sleep(30)
        if ctx.channel_id in _trivia:
            del _trivia[ctx.channel_id]
            try:
                if _rest:
                    await _rest.create_message(
                        ctx.channel_id,
                        f"⏰ Time's up! The correct answer was **{answer_letter}. {correct}**."
                    )
            except Exception:
                pass


@loader.listener(hikari.GuildMessageCreateEvent)
async def on_trivia_answer(event: hikari.GuildMessageCreateEvent) -> None:
    if event.author.is_bot or not event.content or _rest is None:
        return
    session = _trivia.get(event.channel_id)
    if not session:
        return
    answer = event.content.strip().upper()
    if answer not in ("A", "B", "C", "D"):
        return
    if answer == session["answer"]:
        del _trivia[event.channel_id]
        await _rest.create_message(
            event.channel_id,
            f"✅ {event.author.mention} got it right! The answer was **{session['answer']}. {session['full_answer']}**."
        )


@loader.command
class Hangman(lightbulb.SlashCommand, name="hangman", description="Play a game of hangman."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if ctx.channel_id in _hangman:
            await ctx.respond("❌ A hangman game is already active in this channel!")
            return

        word = random.choice(WORDS)
        _hangman[ctx.channel_id] = {
            "word": word,
            "guessed": set(),
            "wrong": 0,
            "expires_at": asyncio.get_event_loop().time() + 300,
        }
        display = " ".join("_" for _ in word)
        await ctx.respond(
            f"{HANGMAN_STAGES[0]}\nWord: `{display}`\n*Guess by typing a single letter!*"
        )
