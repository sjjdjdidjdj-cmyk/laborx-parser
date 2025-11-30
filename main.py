"""
Here's class Parser itself.
Now all code via this file because there is no need for anything else.
With growth of difficulty and volume of code will be created full-fledged src
directory (tests also isn't needed because codebase is very simple).
"""

import re
import html
import asyncio
import logging

from typing import cast
from pathlib import Path

from dotenv import get_key
from aiogram import F, Bot, Dispatcher
from aiohttp import ClientSession
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from selectolax.lexbor import LexborHTMLParser

URL = "https://laborx.com/jobs"
SLEEP_BETWEEN_INTERACTIONS = 180

logging.basicConfig(level="INFO")
logger = logging.getLogger(name="logger")


class Parser:
    """Very simple Parser of LaborX."""

    def __init__(self) -> None:
        """Initialize a new Parser."""
        self.bot: Bot = Bot(token=cast("str", get_key(".env", "TOKEN")))
        self.dp: Dispatcher = Dispatcher()

        self.id_admins: list[str] = [
            key.strip()
            for key in cast("str", get_key(".env", "ID")).split(",")
        ]
        self.task: asyncio.Task[None] | None = None

        logger.info("Initialised.")

    async def run(self) -> None:
        """Run the parser and bot polling."""
        _ = self.dp.callback_query.register(
            self._delete_message_callback, F.data == "delete_message"
        )
        self.dp.startup.register(self.start_parsing)
        self.dp.shutdown.register(self.stop_parsing)
        await self.dp.start_polling(self.bot)  # pyright: ignore[reportUnknownMemberType]

    async def start_parsing(self) -> None:
        """Start parsing (creates asyncio.Task to background)."""
        self.task = asyncio.create_task(self.parsing())
        logger.info("Parsing started.")

    async def stop_parsing(self) -> None:
        """Stop parsing (stop background task of parsing)."""
        if self.task is not None:
            try:
                _ = self.task.cancel()
                await self.task
            except asyncio.CancelledError:
                return
            logger.info("Parsing stoped.")
        else:
            logger.error("Error stopping parsing: parsing not started.")

    async def parsing(self) -> None:
        """Main method for parsing. Infinite loop."""
        try:
            with Path("links.txt").open() as file:  # noqa: ASYNC230
                links = {
                    link.strip()
                    for link in file.read().splitlines()
                    if link.strip()
                }
                logger.info(f"All current links number: {len(links)}")
        except FileNotFoundError:
            links: set[str] = set()
            logger.info("File with links not found")

        while True:
            try:
                async with ClientSession() as client:
                    logger.info("Started new ClientSession.")
                    new_links: set[str] = set()

                    r = await client.get(URL)
                    logger.info(f"On {URL}")

                    for node in LexborHTMLParser(await r.text()).css(
                        ".root.job-card.child-card"
                    ):
                        try:
                            link: str = (  # pyright: ignore[reportUnknownVariableType, reportOperatorIssue]
                                "https://laborx.com"
                                + node.css_first(
                                    ".job-title.job-link.row"
                                ).attributes["href"]
                            )
                            if link not in links:
                                logger.info(f"New link: {link}")
                                new_links.add(cast("str", link))
                        except (KeyError, TypeError):
                            logger.exception(
                                "Error getting link from main page:"
                            )

                    for link in new_links:
                        await self._parse_link(client, link)

                        links.add(link)
                        with Path("links.txt").open("a") as file:  # noqa: ASYNC230
                            _ = file.write("\n" + link)
                    await asyncio.sleep(SLEEP_BETWEEN_INTERACTIONS)
            except (asyncio.CancelledError, KeyboardInterrupt):
                raise
            except BaseException:
                logger.exception("Critical error of work:")

    async def _parse_link(self, client: ClientSession, link: str):
        logger.info(f"Parsing new link {link}")

        try:
            r = await client.get(link)
            parser = LexborHTMLParser(await r.text())

            title = parser.css_first(".job-name").text().strip()
            publish_date = parser.css_first(".publish-date").text().strip()
            price = parser.css_first(".info-value").text().strip() + " $"

            user: str = (  # pyright: ignore[reportOperatorIssue, reportUnknownVariableType]
                "https://laborx.com"
                + parser.css_first(".user-name.link").attributes["href"]
            )

            skills: list[str] = [
                skill.text().strip()
                for skill in parser.css_first(".skills-container").css(
                    ".tag.clickable"
                )
            ]

            try:
                end_date = (
                    parser.css_first(".info-item.day-info")
                    .css_first(".gray-info")
                    .text()
                    .strip()
                    .removeprefix("(till")
                    .rstrip(")")
                    .strip()
                )
            except (KeyError, TypeError, AttributeError):
                end_date = "Not established"

            description = parser.css_first(".description")
            description = description.html
            description = re.sub(  # pyright: ignore[reportUnknownVariableType, reportCallIssue]
                r"<br\s*/?>",
                "\n",
                description,  # pyright: ignore[reportArgumentType]
                flags=re.IGNORECASE,
            )
            description = re.sub(
                r"</p>",
                "\n",
                description,  # pyright: ignore[reportUnknownArgumentType]
                flags=re.IGNORECASE,
            )
            description = re.sub(r"<[^>]+>", "", description)
            description = html.unescape(description).strip()

            await self._send_message(
                link=link,
                title=title,
                description=description,
                publish_date=publish_date,
                end_date=end_date,
                price=price,
                user=cast("str", user),
                skills=skills,
            )
        except (asyncio.CancelledError, KeyboardInterrupt):
            raise
        except Exception:
            logger.exception(f"Error parsing new link {link}")

    async def _send_message(  # noqa: PLR0913
        self,
        link: str,
        title: str,
        description: str,
        publish_date: str,
        end_date: str,
        price: str,
        user: str,
        skills: list[str],
    ) -> None:
        text = (
            f"<b>{html.escape(title)}</b>\n\n"  # noqa: ISC002
            f"<i>{html.escape(description)}</i>\n\n"  # noqa: ISC002
            f"<b>Publish Date:</b> {html.escape(publish_date)}\n"  # noqa: ISC002
            f"<b>End Date:</b> {html.escape(end_date)}\n"  # noqa: ISC002
            f"<b>Price:</b> {html.escape(price)}\n\n"  # noqa: ISC002
            f"<b>Skills:</b> {html.escape(', '.join(skills))}"
        )
        logger.info("Sending message for admins")

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="User Profile",
                        url=user,
                    ),
                    InlineKeyboardButton(
                        text="Job Link",
                        url=link,
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Delete Message",
                        callback_data="delete_message",
                    )
                ],
            ]
        )

        for admin_id in self.id_admins:
            try:
                _ = await self.bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            except (KeyboardInterrupt, asyncio.CancelledError):
                raise
            except Exception:
                logger.exception(f"Error sending {admin_id}")

    async def _delete_message_callback(
        self, callback_query: CallbackQuery
    ) -> None:
        """Delete message on button click."""
        _ = await callback_query.message.delete()  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
        _ = await callback_query.answer()


async def main() -> None:
    """Point of entry."""
    await Parser().run()


if __name__ == "__main__":
    asyncio.run(main())
