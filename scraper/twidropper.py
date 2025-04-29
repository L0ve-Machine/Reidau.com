# scraper/twidropper.py
import re, requests, logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin

logger = logging.getLogger(__name__)
ENDP = "https://twidropper.com/en"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

def fetch_from_twidropper(tweet_url: str) -> str | None:
    try:
        r = requests.get(
            ENDP,
            params={"url": tweet_url},
            headers={"User-Agent": UA},
            timeout=15,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        link = soup.find("a", attrs={"download": True}, href=re.compile(r"\.mp4$"))
        return urljoin(ENDP, link["href"]) if link else None
    except Exception as e:
        logger.warning(f"Twidropper failed: {e}")
        return None
