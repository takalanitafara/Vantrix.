from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
import runpy

import pytest
from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.ids = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a':
            self.links.append(attrs.get('href', ''))


def test_home_is_complete_html():
    response = client.get('/')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/html')
    page = PageParser()
    page.feed(response.text)
    for tag in ('html', 'head', 'title', 'body', 'main', 'footer', 'script'):
        assert tag in page.tags
    assert response.text.rstrip().endswith('</html>')
    assert len(page.ids) == len(set(page.ids))
    assert all(link[1:] in page.ids for link in page.links if link.startswith('#'))
    assert 'Prototype' in response.text


def test_health():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'ok': True, 'service': 'Vantrix', 'status': 'running'}


def test_unknown_route():
    assert client.get('/does-not-exist').status_code == 404


def test_home_does_not_depend_on_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert client.get('/').status_code == 200


@pytest.mark.parametrize('port,expected', [(None, 8000), ('8123', 8123)])
def test_startup_port(monkeypatch, port, expected):
    if port is None:
        monkeypatch.delenv('PORT', raising=False)
    else:
        monkeypatch.setenv('PORT', port)
    with patch('uvicorn.run') as run:
        runpy.run_path(str(Path(__file__).resolve().parents[1] / 'server.py'), run_name='__main__')
    assert run.call_args.kwargs == {'host': '0.0.0.0', 'port': expected}
