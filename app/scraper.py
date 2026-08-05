import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from bs4.element import Tag


@dataclass(frozen=True)
class ScrapedPage:
    title: str
    text: str


class Scraper:
    _MAX_RESPONSE_BYTES = 10 * 1024 * 1024
    _BLOCK_TAGS = (
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "li",
        "blockquote",
        "pre",
        "figcaption",
    )
    _NOISE_PATTERN = re.compile(
        r"(?:^|[-_\s])(?:advert(?:isement)?|ads?|breadcrumb|cookie|consent|"
        r"comments?|byline|author|article-meta|post-meta|copyright|menu|"
        r"nav(?:igation)?|newsletter|pagination|popup|promo|"
        r"recommend(?:ed|ations?)?|related|share|sidebar|social|subscribe|"
        r"toolbar)(?:$|[-_\s])",
        re.IGNORECASE,
    )
    _BOILERPLATE_HEADINGS = {
        "bibliography",
        "citations",
        "external links",
        "footnotes",
        "further reading",
        "references",
        "see also",
        "각주",
        "같이 보기",
        "더 읽어보기",
        "외부 링크",
        "참고 문헌",
        "참고문헌",
    }

    @classmethod
    def scrape(cls, url: str) -> ScrapedPage:
        soup = BeautifulSoup(cls._read_url(url), "html.parser")
        title = cls._page_title(soup, url)
        cls._remove_noise(soup)
        content = cls._select_fragment(soup, url) or cls._select_content(soup)
        return ScrapedPage(title, cls._extract_text(content))

    @classmethod
    def _select_fragment(cls, soup: BeautifulSoup, url: str) -> Tag | None:
        fragment = urlparse(url).fragment
        if not fragment:
            return None

        target = soup.find(id=fragment) or soup.find("a", attrs={"name": fragment})
        if not isinstance(target, Tag):
            return None
        if len(target.get_text(" ", strip=True).split()) >= 20:
            return target

        start = target.find_parent(cls._BLOCK_TAGS) or target
        start_heading_level = cls._heading_level(start)
        siblings = list(start.next_siblings)
        container = soup.new_tag("div")
        container.append(start.extract())
        for sibling in siblings:
            if not isinstance(sibling, Tag):
                continue
            sibling_heading_level = cls._heading_level(sibling)
            if (
                start_heading_level is not None
                and sibling_heading_level is not None
                and sibling_heading_level <= start_heading_level
            ) or (
                start_heading_level is None
                and sibling.name == start.name
                and sibling.find("a", attrs={"name": True})
            ):
                break
            container.append(sibling.extract())
        return container

    @classmethod
    def _remove_noise(cls, soup: BeautifulSoup) -> None:
        for element in soup(
            [
                "script",
                "style",
                "noscript",
                "template",
                "svg",
                "canvas",
                "iframe",
                "form",
                "button",
                "dialog",
                "nav",
                "footer",
                "aside",
            ]
        ):
            element.decompose()

        for element in list(soup.find_all(True)):
            if element.name is None or element.attrs is None:
                continue
            if element.name in {"html", "body"}:
                continue
            role = element.get("role", "").lower()
            attributes = " ".join(
                [element.get("id", ""), *element.get("class", [])]
            )
            if (
                element.has_attr("hidden")
                or element.get("aria-hidden", "").lower() == "true"
                or role
                in {"banner", "complementary", "contentinfo", "dialog", "navigation"}
            ):
                element.decompose()
            elif cls._NOISE_PATTERN.search(attributes):
                element.decompose()

        for header in list(soup.find_all("header")):
            if header.find_parent(["article", "main"]) is None:
                header.decompose()

    @classmethod
    def _select_content(cls, soup: BeautifulSoup) -> Tag:
        semantic_candidates = soup.select("article, main, [role='main']")
        if semantic_candidates:
            return max(semantic_candidates, key=cls._content_score)

        candidates = [
            element
            for element in soup.find_all(["section", "div"])
            if len(element.get_text(" ", strip=True).split()) >= 20
        ]
        if candidates:
            return max(candidates, key=cls._content_score)

        content = soup.body or soup
        for header in list(content.find_all("header")):
            header.decompose()
        return content

    @classmethod
    def _content_score(cls, element: Tag) -> int:
        text_length = len(element.get_text(" ", strip=True))
        link_length = sum(
            len(link.get_text(" ", strip=True)) for link in element.find_all("a")
        )
        paragraph_count = len(element.find_all("p"))
        return text_length - (2 * link_length) + (100 * paragraph_count)

    @classmethod
    def _extract_text(cls, content: Tag) -> str:
        blocks: list[tuple[str, bool]] = []
        had_text_blocks = False
        skipped_heading_level: int | None = None
        for element in content.find_all(cls._BLOCK_TAGS):
            if cls._has_block_ancestor(element, content):
                continue
            text = cls._clean_text(element.get_text(" ", strip=True))
            if not text:
                continue
            had_text_blocks = True

            heading_level = cls._heading_level(element)
            if skipped_heading_level is not None:
                if heading_level is None or heading_level > skipped_heading_level:
                    continue
                skipped_heading_level = None

            if (
                heading_level is not None
                and cls._normalize_heading(text) in cls._BOILERPLATE_HEADINGS
            ):
                skipped_heading_level = heading_level
                continue

            link_text_length = sum(
                len(link.get_text(" ", strip=True)) for link in element.find_all("a")
            )
            link_heavy = link_text_length / len(text) >= 0.8
            if not blocks or text != blocks[-1][0]:
                blocks.append((text, link_heavy))

        while blocks and blocks[-1][1]:
            blocks.pop()
        if blocks:
            return "\n\n".join(text for text, _ in blocks)
        if had_text_blocks:
            return ""
        return " ".join(content.get_text(" ", strip=True).split())

    @staticmethod
    def _heading_level(element: Tag) -> int | None:
        if re.fullmatch(r"h[1-6]", element.name or ""):
            return int(element.name[1])
        return None

    @staticmethod
    def _normalize_heading(text: str) -> str:
        return re.sub(r"[^\w\s]", "", text, flags=re.UNICODE).casefold().strip()

    @staticmethod
    def _clean_text(text: str) -> str:
        text = " ".join(text.split())
        return re.sub(r"\s+([,.;:!?])", r"\1", text)

    @classmethod
    def _has_block_ancestor(cls, element: Tag, content: Tag) -> bool:
        parent = element.parent
        while isinstance(parent, Tag) and parent is not content:
            if parent.name in cls._BLOCK_TAGS:
                return True
            parent = parent.parent
        return False

    @staticmethod
    def _page_title(soup: BeautifulSoup, url: str) -> str:
        for selector in (
            'meta[property="og:title"]',
            'meta[name="twitter:title"]',
        ):
            metadata = soup.select_one(selector)
            if metadata is not None and metadata.get("content", "").strip():
                return metadata["content"].strip()
        if soup.title is not None:
            title = soup.title.get_text(" ", strip=True)
            if title:
                return title
        parsed_url = urlparse(url)
        return Path(parsed_url.path).stem or parsed_url.netloc or "Imported document"

    @staticmethod
    def _read_url(url: str) -> str:
        request = Request(
            Scraper._request_url(url),
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "Luculent/1.0",
            },
        )
        with urlopen(request, timeout=15) as response:
            content_type = response.headers.get("Content-Type")
            if content_type:
                media_type = content_type.split(";", 1)[0].strip().lower()
                if media_type not in {"text/html", "application/xhtml+xml"}:
                    raise ValueError(f"Unsupported content type: {media_type}")
            charset = response.headers.get_content_charset() or "utf-8"
            content = response.read(Scraper._MAX_RESPONSE_BYTES + 1)
            if len(content) > Scraper._MAX_RESPONSE_BYTES:
                raise ValueError("Page exceeds the maximum supported size")
            return content.decode(charset, errors="replace")

    @staticmethod
    def _request_url(url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError("URL must use HTTP or HTTPS")
        hostname = parsed.hostname.encode("idna").decode("ascii") if parsed.hostname else ""
        if parsed.port:
            hostname = f"{hostname}:{parsed.port}"
        if parsed.username:
            credentials = quote(parsed.username, safe="")
            if parsed.password:
                credentials += f":{quote(parsed.password, safe='')}"
            hostname = f"{credentials}@{hostname}"
        return urlunsplit(
            (
                parsed.scheme,
                hostname,
                quote(parsed.path, safe="/%:@"),
                quote(parsed.query, safe="=&;%:+,/?@"),
                "",
            )
        )
