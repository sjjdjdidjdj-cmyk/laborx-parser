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
from aiogram import Bot
from camoufox import AsyncCamoufox
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from selectolax.lexbor import LexborHTMLParser
from playwright.async_api import Page

URL = "https://laborx.com/jobs"
SLEEP_BETWEEN_INTERACTIONS = 180

logging.basicConfig(level="INFO")
logger = logging.getLogger(name="logger")


class Parser:
    """Very simple Parser of LaborX."""

    def __init__(self) -> None:
        """Initialize a new Parser."""
        self.bot: Bot = Bot(token=cast("str", get_key(".env", "TOKEN")))
        self.id_admins: list[str] = [
            key.strip()
            for key in cast("str", get_key(".env", "ID")).split(",")
        ]
        self.task: asyncio.Task[None] | None = None
        logger.info("Initialised.")

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
                async with AsyncCamoufox(
                    firefox_user_prefs={
                        "network.proxy.type": 0,
                    },
                    headless=True,
                ) as browser:
                    logger.info("Started new browser.")
                    new_links: set[str] = set()

                    page = await browser.new_page()
                    _ = await page.goto(URL)
                    logger.info(f"On {URL}")

                    for node in LexborHTMLParser(await page.content()).css(
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
                        await self._parse_link(page, link)

                        links.add(link)
                        with Path("links.txt").open("a") as file:  # noqa: ASYNC230
                            _ = file.write("\n" + link)
                    await asyncio.sleep(SLEEP_BETWEEN_INTERACTIONS)
            except asyncio.CancelledError:
                raise
            except BaseException:
                logger.exception("Critical error of work:")

    async def _parse_link(self, page: Page, link: str):
        for attempt in range(4):
            logger.info(f"Parsing new link {link} attempt {attempt}")
            try:
                _ = await page.goto(link)

                await asyncio.sleep(delay=cast("int", 2**attempt))

                parser = LexborHTMLParser(await page.content())

                title = parser.css_first(".job-name").text().strip()
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

                publish_date = parser.css_first(".publish-date").text().strip()
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
            except Exception:
                logger.exception(f"Error parsing new link {link}")
            else:
                break

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
                ]
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
            except Exception:
                logger.exception(f"Ошибка отправления сообщения {admin_id}")


async def main() -> None:
    """Point of entry."""
    parser = Parser()
    await parser.start_parsing()
    await asyncio.sleep(99999)


if __name__ == "__main__":
    asyncio.run(main())
