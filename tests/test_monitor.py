from monitor import PageMonitor
from unittest.mock import MagicMock, patch

def test_clean_content():
    html = "<html><script>var x=1;</script><body><style>body{color:red;}</style><p>Hello World</p></body></html>"
    text = PageMonitor.clean_content(html)
    assert text == "Hello World"

def test_get_content_hash():
    text = "Hello World"
    # echo -n "Hello World" | shasum -a 256
    expected = "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e"
    assert PageMonitor.get_content_hash(text) == expected

@patch("monitor.PageMonitor.fetch_content")
def test_check_for_changes_new(mock_fetch):
    mock_fetch.return_value = "<html>Hello</html>"
    
    new_hash, changed, summary = PageMonitor.check_for_changes("http://example.com", None)
    
    assert changed is False
    assert "Initial check" in summary
    assert new_hash is not None

@patch("monitor.PageMonitor.fetch_content")
def test_check_for_changes_no_change(mock_fetch):
    mock_fetch.return_value = "<html>Hello</html>"
    # Pre-calculate hash
    old_hash = PageMonitor.get_content_hash("Hello")
    
    new_hash, changed, summary = PageMonitor.check_for_changes("http://example.com", old_hash)
    
    assert changed is False
    assert new_hash == old_hash
    assert summary == "No changes."

@patch("monitor.PageMonitor.fetch_content")
def test_check_for_changes_changed(mock_fetch):
    mock_fetch.return_value = "<html>Hello Changed</html>"
    old_hash = PageMonitor.get_content_hash("Hello")
    
    new_hash, changed, summary = PageMonitor.check_for_changes("http://example.com", old_hash)
    
    assert changed is True
    assert new_hash != old_hash
    assert "Content changed" in summary

@patch("monitor.PageMonitor.fetch_content")
def test_check_for_changes_fetch_fail(mock_fetch):
    mock_fetch.return_value = None
    
    new_hash, changed, summary = PageMonitor.check_for_changes("http://example.com", "oldhash")
    
    assert changed is False
    assert new_hash == "oldhash"
    assert "Failed to fetch" in summary

@patch("monitor.requests.get")
def test_fetch_content_exception(mock_get):
    from requests import RequestException
    mock_get.side_effect = RequestException("Boom")
    
    content = PageMonitor.fetch_content("http://bad.com")
    assert content is None

@patch("monitor.requests.get")
def test_fetch_content_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.text = "ok"
    mock_get.return_value = mock_resp
    
    content = PageMonitor.fetch_content("http://good.com")
    assert content == "ok"
