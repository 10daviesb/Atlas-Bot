import asyncio
import html
import random

import aiohttp
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Games")

TRIVIA_URL = "https://opentdb.com/api.php?amount=1&type=multiple"
TRIVIA_TIMEOUT = 20  # seconds to answer

# channel_id -> {answer, correct_text, task}
_trivia: dict[int, dict] = {}

# channel_id -> {word, guessed, lives}
_hangman: dict[int, dict] = {}

HANGMAN_WORDS = [
    "python", "discord", "server", "keyboard", "monitor", "developer",
    "function", "variable", "database", "extension", "permission", "channel",
    "moderator", "streaming", "community", "leaderboard", "notification",
    "attachment", "encryption", "bandwidth", "algorithm", "framework",
]

HANGMAN_ART = [
    "```\n +---+\n |   |\n     |\n     |\n     |\n     |\n=========```",
    "```\n +---+\n |   |\n O   |\n     |\n     |\n     |\n=========```",
    "```\n +---+\n |   |\n O   |\n |   |\n     |\n     |\n=========```",
    "```\n +---+\n |   |\n O   |\n/|   |\n     |\n     |\n=========```",
    "```\n +---+\n |   |\n O   |\n/|\\  |\n     |\n     |\n=========```",
    "```\n +---+\n |   |\n O   |\n/|\\  |\n/    |\n     |\n=========```",
    "```\n +---+\n |   |\n O   |\n/|\\  |\n/ \\  |\n     |\n=========```",
]
MAX_LIVES = len(HANGMAN_ART) - 1

LETTER_EMOJIS = {"A": "🇦", "B": "🇧", "C": "🇨", "D": "🇩"}


def _mask(word: str, guessed: set[str]) -> str:
    return " ".join(c if c in guessed else "\_" for c in word)


# ── Trivia ───────────────────────────────────────────────────────────────────

@plugin.command()
@lightbulb.command("trivia", "Answer a random trivia question.")
@lightbulb.implements(lightbulb.SlashCommand)
async def trivia(ctx: lightbulb.Context) -> None:
    if ctx.channel_id in _trivia:
        await ctx.respond("❌ There's already an active trivia question here. Use `/answer`.")
        return

    async with aiohttp.ClientSession() as session:
        async with session.get(TRIVIA_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()

    if data.get("response_code") != 0 or not data.get("results"):
        await ctx.respond("❌ Couldn't fetch a question. Try again.")
        return

    q = data["results"][0]
    question = html.unescape(q["question"])
    correct = html.unescape(q["correct_answer"])
    choices = [html.unescape(a) for a in q["incorrect_answers"]] + [correct]
    random.shuffle(choices)
    correct_letter = "ABCD"[choices.index(correct)]

    lines = [f"**{question}**\n"]
    for letter, choice in zip("ABCD", choices):
        lines.append(f"{LETTER_EMOJIS[letter]} **{letter}.** {choice}")
    lines.append(f"\n*You have {TRIVIA_TIMEOUT} seconds — use `/answer A/B/C/D`*")

    await ctx.respond("\n".join(lines))

    async def expire() -> None:
        await asyncio.sleep(TRIVIA_TIMEOUT)
        if ctx.channel_id in _trivia:
            del _trivia[ctx.channel_id]
            await plugin.bot.rest.create_message(
                ctx.channel_id,
                f"⏰ Time's up! The answer was **{correct_letter}. {correct}**."
            )

    _trivia[ctx.channel_id] = {
        "answer": correct_letter,
        "correct_text": correct,
        "task": asyncio.create_task(expire()),
    }
    logger.info(f"Trivia started in channel {ctx.channel_id}")


@plugin.command()
@lightbulb.option("choice", "Your answer: A, B, C, or D.", type=str)
@lightbulb.command("answer", "Answer the current trivia question.")
@lightbulb.implements(lightbulb.SlashCommand)
async def answer(ctx: lightbulb.Context) -> None:
    game = _trivia.get(ctx.channel_id)
    if not game:
        await ctx.respond("❌ No active trivia question. Use `/trivia` to start one.")
        return

    guess = ctx.options.choice.strip().upper()
    if guess not in "ABCD" or len(guess) != 1:
        await ctx.respond("❌ Answer must be A, B, C, or D.")
        return

    game["task"].cancel()
    del _trivia[ctx.channel_id]

    if guess == game["answer"]:
        await ctx.respond(
            f"✅ Correct, {ctx.author.mention}! The answer was **{game['answer']}. {game['correct_text']}**."
        )
    else:
        await ctx.respond(
            f"❌ Wrong! The correct answer was **{game['answer']}. {game['correct_text']}**."
        )


# ── Hangman ──────────────────────────────────────────────────────────────────

@plugin.command()
@lightbulb.command("hangman", "Start a game of hangman.")
@lightbulb.implements(lightbulb.SlashCommand)
async def hangman(ctx: lightbulb.Context) -> None:
    if ctx.channel_id in _hangman:
        await ctx.respond("❌ There's already an active hangman game here. Use `/guess`.")
        return

    word = random.choice(HANGMAN_WORDS)
    _hangman[ctx.channel_id] = {"word": word, "guessed": set(), "lives": MAX_LIVES}

    await ctx.respond(
        f"{HANGMAN_ART[0]}\n"
        f"**Word:** `{_mask(word, set())}`\n"
        f"Lives: {'❤️' * MAX_LIVES}\n"
        f"Use `/guess <letter>` to guess a letter!"
    )
    logger.info(f"Hangman started in channel {ctx.channel_id}")


@plugin.command()
@lightbulb.option("letter", "A single letter to guess.", type=str)
@lightbulb.command("guess", "Guess a letter in the active hangman game.")
@lightbulb.implements(lightbulb.SlashCommand)
async def guess(ctx: lightbulb.Context) -> None:
    game = _hangman.get(ctx.channel_id)
    if not game:
        await ctx.respond("❌ No active hangman game. Use `/hangman` to start one.")
        return

    letter = ctx.options.letter.strip().lower()
    if len(letter) != 1 or not letter.isalpha():
        await ctx.respond("❌ Please guess a single letter.")
        return

    if letter in game["guessed"]:
        await ctx.respond(f"❌ `{letter}` was already guessed!")
        return

    game["guessed"].add(letter)
    word = game["word"]
    hit = letter in word

    if not hit:
        game["lives"] -= 1

    stage = HANGMAN_ART[MAX_LIVES - game["lives"]]
    masked = _mask(word, game["guessed"])
    guessed_str = " ".join(sorted(game["guessed"]))

    if "_" not in masked.replace(" ", ""):
        del _hangman[ctx.channel_id]
        await ctx.respond(f"{stage}\n🎉 **You won!** The word was **{word}**!")
        return

    if game["lives"] <= 0:
        del _hangman[ctx.channel_id]
        await ctx.respond(f"{stage}\n💀 **Game over!** The word was **{word}**.")
        return

    result_line = f"✅ `{letter}` is in the word!" if hit else f"❌ No `{letter}` in the word."
    await ctx.respond(
        f"{result_line}\n"
        f"{stage}\n"
        f"**Word:** `{masked}`\n"
        f"Lives: {'❤️' * game['lives']}\n"
        f"Guessed: `{guessed_str or 'none'}`"
    )


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Games extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Games extension unloaded.")
