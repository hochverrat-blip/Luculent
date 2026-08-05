from email.message import Message

import pytest

import app.scraper as scraper_module
from app.scraper import Scraper


def test_scraper_extracts_article_content(monkeypatch):
    html = """
        <html>
          <head><title>Reading title</title><style>hidden style</style></head>
          <body>
            <nav>Site navigation</nav>
            <article>
              <h1>Article heading</h1>
              <p>First paragraph.</p>
              <script>hidden script</script>
              <div class="social-share">Share this article</div>
              <p>Second.</p>
              <section class="related-articles">You may also like</section>
            </article>
            <footer>Site footer</footer>
          </body>
        </html>
    """
    monkeypatch.setattr(
        Scraper,
        "_read_url",
        staticmethod(lambda url: html),
    )

    page = Scraper.scrape("https://example.com/article")

    assert page.title == "Reading title"
    assert page.text == "Article heading\n\nFirst paragraph.\n\nSecond."


def test_scraper_uses_url_as_title_when_page_has_no_title(monkeypatch):
    monkeypatch.setattr(
        Scraper,
        "_read_url",
        staticmethod(lambda url: "<main>Document text</main>"),
    )

    page = Scraper.scrape("https://example.com/articles/reading")

    assert page.title == "reading"
    assert page.text == "Document text"


def test_scraper_prefers_main_content_and_preserves_reading_blocks(monkeypatch):
    html = """
        <body>
          <header>Website masthead</header>
          <main>
            <h1>Main heading</h1>
            <p>A paragraph with <strong>inline emphasis</strong> intact.</p>
            <ul><li>First item</li><li>Second item</li></ul>
          </main>
          <div class="newsletter-popup">Join our newsletter</div>
        </body>
    """
    monkeypatch.setattr(Scraper, "_read_url", staticmethod(lambda url: html))

    page = Scraper.scrape("https://example.com/main")

    assert page.text == (
        "Main heading\n\n"
        "A paragraph with inline emphasis intact.\n\n"
        "First item\n\nSecond item"
    )


def test_scraper_finds_content_without_semantic_article_tags(monkeypatch):
    article_text = " ".join(f"article-word-{index}" for index in range(30))
    html = f"""
        <body>
          <header>Website masthead</header>
          <div class="menu">Menu item one Menu item two</div>
          <div id="story-content"><p>{article_text}</p></div>
          <div class="comments">Meanie41: This article sucks!</div>
          <footer>Copyright notice</footer>
        </body>
    """
    monkeypatch.setattr(Scraper, "_read_url", staticmethod(lambda url: html))

    page = Scraper.scrape("https://example.com/story")

    assert page.text == article_text


def test_scraper_removes_metadata_and_hidden_content(monkeypatch):
    html = """
        <head>
          <title>Site title</title>
          <meta property="og:title" content="Article title">
        </head>
        <article>
          <div class="byline">By Example Author</div>
          <p>Visible article text.</p>
          <p aria-hidden="true">Hidden duplicate text.</p>
          <dialog>Subscription prompt</dialog>
        </article>
    """
    monkeypatch.setattr(Scraper, "_read_url", staticmethod(lambda url: html))

    page = Scraper.scrape("https://example.com/article")

    assert page.title == "Article title"
    assert page.text == "Visible article text."


def test_scraper_handles_nested_noise_elements(monkeypatch):
    html = """
        <article>
          <div class="comments"><p>Nested comment text</p></div>
          <p>Article text</p>
        </article>
    """
    monkeypatch.setattr(Scraper, "_read_url", staticmethod(lambda url: html))

    page = Scraper.scrape("https://example.com/article")

    assert page.text == "Article text"


def test_scraper_removes_copyright_content_inside_main(monkeypatch):
    html = """
        <main>
          <p>Article text.</p>
          <div class="copyright-text"><p>Company and regional site links.</p></div>
        </main>
    """
    monkeypatch.setattr(Scraper, "_read_url", staticmethod(lambda url: html))

    page = Scraper.scrape("https://example.com/article")

    assert page.text == "Article text."


def test_scraper_does_not_remove_page_for_noise_words_on_root(monkeypatch):
    html = """
        <html class="site-main-menu-disabled">
          <body><main><p>Article text</p></main></body>
        </html>
    """
    monkeypatch.setattr(Scraper, "_read_url", staticmethod(lambda url: html))

    page = Scraper.scrape("https://example.com/article")

    assert page.text == "Article text"


def test_scraper_limits_old_style_page_to_named_fragment(monkeypatch):
    html = """
        <body>
          <h3 class="story"><a name="Story-1"></a>First story</h3>
          <p>First story text.</p>
          <h3 class="story"><a name="Story-2"></a>Second story</h3>
          <p>Second story text.</p>
        </body>
    """
    monkeypatch.setattr(Scraper, "_read_url", staticmethod(lambda url: html))

    page = Scraper.scrape("https://example.com/stories#Story-1")

    assert page.text == "First story\n\nFirst story text."


def test_scraper_limits_modern_id_fragment_to_its_heading_section(monkeypatch):
    html = """
        <main>
          <h2 id="first">First section</h2>
          <p>First section text.</p>
          <h3>First subsection</h3>
          <p>Subsection text.</p>
          <h2 id="second">Second section</h2>
          <p>Second section text.</p>
        </main>
    """
    monkeypatch.setattr(Scraper, "_read_url", staticmethod(lambda url: html))

    page = Scraper.scrape("https://example.com/article#first")

    assert page.text == (
        "First section\n\nFirst section text.\n\n"
        "First subsection\n\nSubsection text."
    )


def test_scraper_removes_boilerplate_sections_but_preserves_later_content(
    monkeypatch,
):
    html = """
        <article>
          <h1>Article</h1>
          <p>Main text.</p>
          <h2>References</h2>
          <p>A source that should not be stored.</p>
          <h3>Books</h3>
          <p>Another source that should not be stored.</p>
          <h2>Appendix</h2>
          <p>Useful appendix text.</p>
        </article>
    """
    monkeypatch.setattr(Scraper, "_read_url", staticmethod(lambda url: html))

    page = Scraper.scrape("https://example.com/article")

    assert page.text == "Article\n\nMain text.\n\nAppendix\n\nUseful appendix text."


def test_scraper_removes_korean_boilerplate_sections(monkeypatch):
    html = """
        <article>
          <h1>본문</h1>
          <p>저장할 내용입니다.</p>
          <h2>각주</h2>
          <p>저장하지 않을 출처입니다.</p>
          <h2>외부 링크</h2>
          <p>저장하지 않을 링크입니다.</p>
        </article>
    """
    monkeypatch.setattr(Scraper, "_read_url", staticmethod(lambda url: html))

    page = Scraper.scrape("https://example.com/article")

    assert page.text == "본문\n\n저장할 내용입니다."


def test_scraper_preserves_reference_words_and_inline_links(monkeypatch):
    html = """
        <article>
          <p>This paragraph references an <a href="/example">important example</a>.</p>
          <p>It remains part of the article.</p>
        </article>
    """
    monkeypatch.setattr(Scraper, "_read_url", staticmethod(lambda url: html))

    page = Scraper.scrape("https://example.com/article")

    assert page.text == (
        "This paragraph references an important example.\n\n"
        "It remains part of the article."
    )


def test_scraper_removes_link_heavy_blocks_only_from_the_end(monkeypatch):
    html = """
        <article>
          <ul><li><a href="/topic">Topic navigation</a></li></ul>
          <p>Article text.</p>
          <ul>
            <li><a href="/category-one">Category one</a></li>
            <li><a href="/category-two">Category two</a></li>
          </ul>
        </article>
    """
    monkeypatch.setattr(Scraper, "_read_url", staticmethod(lambda url: html))

    page = Scraper.scrape("https://example.com/article")

    assert page.text == "Topic navigation\n\nArticle text."


def test_scraper_encodes_unicode_request_urls():
    url = "https://namu.wiki/w/웹소설/시장?검색어=한국어#section"

    request_url = Scraper._request_url(url)

    assert request_url == (
        "https://namu.wiki/w/%EC%9B%B9%EC%86%8C%EC%84%A4/"
        "%EC%8B%9C%EC%9E%A5?%EA%B2%80%EC%83%89%EC%96%B4="
        "%ED%95%9C%EA%B5%AD%EC%96%B4"
    )


def test_scraper_does_not_restore_discarded_blocks(monkeypatch):
    html = """
        <article>
          <h2>References</h2>
          <p>Discarded source.</p>
        </article>
    """
    monkeypatch.setattr(Scraper, "_read_url", staticmethod(lambda url: html))

    page = Scraper.scrape("https://example.com/article")

    assert page.text == ""


@pytest.mark.parametrize("url", ["file:///private.txt", "ftp://example.com/file"])
def test_scraper_rejects_non_http_urls(url):
    with pytest.raises(ValueError, match="HTTP or HTTPS"):
        Scraper._request_url(url)


def test_scraper_rejects_non_html_content(monkeypatch):
    response = _FakeResponse(b"binary", "application/pdf")
    monkeypatch.setattr(scraper_module, "urlopen", lambda request, timeout: response)

    with pytest.raises(ValueError, match="Unsupported content type"):
        Scraper._read_url("https://example.com/file.pdf")


def test_scraper_rejects_oversized_pages(monkeypatch):
    monkeypatch.setattr(Scraper, "_MAX_RESPONSE_BYTES", 10)
    response = _FakeResponse(b"01234567890", "text/html; charset=utf-8")
    monkeypatch.setattr(scraper_module, "urlopen", lambda request, timeout: response)

    with pytest.raises(ValueError, match="maximum supported size"):
        Scraper._read_url("https://example.com/large")


class _FakeResponse:
    def __init__(self, content: bytes, content_type: str):
        self._content = content
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        pass

    def read(self, size: int) -> bytes:
        return self._content[:size]
