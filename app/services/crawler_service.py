"""
Website knowledge ingestion: sitemap discovery -> URL filtering -> fetch ->
main-content extraction -> cleaning. Restricted to the target domain only,
with a hard URL count / depth / timeout cap so a crawl can never run away
or touch external domains.
"""
import requests
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree
from bs4 import BeautifulSoup

PRIORITY_PATHS = ["about", "services", "product", "pricing", "faq", "contact", "location"]
SKIP_PATHS = ["login", "account", "cart", "checkout", "privacy", "terms", "signin", "signup"]


def _same_domain(base_domain, url):
    return urlparse(url).netloc.replace("www.", "") == base_domain.replace("www.", "")


def discover_urls(base_url, max_urls=40, timeout=8):
    """Try sitemap.xml first; fall back to a shallow same-domain crawl from robots/home page links."""
    parsed = urlparse(base_url)
    domain = parsed.netloc
    root = f"{parsed.scheme}://{domain}"
    urls = set()

    sitemap_urls = [f"{root}/sitemap.xml"]
    try:
        robots = requests.get(f"{root}/robots.txt", timeout=timeout)
        if robots.ok:
            for line in robots.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sitemap_urls.append(line.split(":", 1)[1].strip())
    except Exception:
        pass

    for sm_url in sitemap_urls:
        try:
            resp = requests.get(sm_url, timeout=timeout)
            if not resp.ok:
                continue
            root_xml = ElementTree.fromstring(resp.content)
            for loc in root_xml.iter():
                if loc.tag.endswith("loc") and loc.text:
                    if _same_domain(domain, loc.text):
                        urls.add(loc.text.strip())
        except Exception:
            continue
        if urls:
            break

    if not urls:
        # Fallback: shallow crawl of the homepage's same-domain links only.
        try:
            resp = requests.get(root, timeout=timeout)
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                link = urljoin(root, a["href"])
                if _same_domain(domain, link):
                    urls.add(link.split("#")[0])
        except Exception:
            pass
        urls.add(root)

    return list(urls)[:max_urls]


def filter_relevant_urls(urls):
    relevant = []
    for u in urls:
        path = urlparse(u).path.lower()
        if any(skip in path for skip in SKIP_PATHS):
            continue
        relevant.append(u)
    # Sort priority pages first
    relevant.sort(key=lambda u: 0 if any(p in u.lower() for p in PRIORITY_PATHS) else 1)
    return relevant


def extract_main_content(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text(separator=" ", strip=True) if main else soup.get_text(" ", strip=True)
    # collapse whitespace
    return " ".join(text.split())


def fetch_page_text(url, timeout=8):
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "ReceptaBot/1.0"})
    resp.raise_for_status()
    title = ""
    try:
        title = BeautifulSoup(resp.text, "html.parser").title.string.strip()
    except Exception:
        pass
    return title, extract_main_content(resp.text)
