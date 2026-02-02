import hashlib
import logging
import requests
from bs4 import BeautifulSoup
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class PageMonitor:
    """
    Stateless page monitor.
    """

    @staticmethod
    def fetch_content(url: str) -> Optional[str]:
        """Fetches the page content."""
        try:
            # Added a user agent to avoid being blocked by some sites
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Error fetching URL {url}: {e}")
            return None

    @staticmethod
    def clean_content(html_content: str) -> str:
        """
        Cleans the HTML content.
        Removes scripts, styles, and extracts text.
        """
        if not html_content:
            return ""
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script and style elements
        for script_or_style in soup(["script", "style", "meta", "noscript"]):
            script_or_style.decompose()

        # Get text content
        text = soup.get_text(separator=" ", strip=True)
        return text

    @staticmethod
    def get_content_hash(text: str) -> str:
        """Returns sha256 hash of the text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @classmethod
    def check_for_changes(cls, url: str, old_hash: Optional[str]) -> Tuple[Optional[str], bool, str]:
        """
        Checks for changes.
        Returns: (new_hash, changed, summary)
        """
        html = cls.fetch_content(url)
        if not html:
            return old_hash, False, "Failed to fetch content."

        text = cls.clean_content(html)
        new_hash = cls.get_content_hash(text)

        if old_hash is None:
            # First run
            return new_hash, False, "Initial check. Monitoring started."

        if new_hash != old_hash:
            # Change detected
            # Try to infer what changed (basic length check)
            # In a real diff implementation, we would compare stored text vs new text,
            # but we only store hash for efficiency in DB.
            # So we can only say "Content changed".
            
            # Simple heuristic if we want to add more detail in future: 
            # Could download "last version" if we stored it, but we don't.
            # length_diff = len(text)  # We can't know the old length from hash.
            summary = f"Content changed. New content length: {len(text)} characters."
            return new_hash, True, summary

        return new_hash, False, "No changes."
