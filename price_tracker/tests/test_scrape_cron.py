"""Tests for the cron scrape helper."""

from tools.scrape import _is_stale_nyon_target


def test_stale_nyon_target_matches_nyon_pages():
    target = {
        'type': 'page',
        'title': 'La Casa Del Habano Nyon',
        'url': 'https://la-casa-del-habano-nyon.com/en/',
    }

    assert _is_stale_nyon_target(target) is True


def test_stale_nyon_target_matches_429_pages():
    target = {
        'type': 'page',
        'title': '429 Too Many Requests',
        'url': 'https://la-casa-del-habano-nyon.com/en/product-category/cigares-cubains/h-upmann/?currency=CHF',
    }

    assert _is_stale_nyon_target(target) is True


def test_stale_nyon_target_ignores_non_nyon_pages():
    target = {
        'type': 'page',
        'title': 'COH China',
        'url': 'https://www.cohcigars.com/',
    }

    assert _is_stale_nyon_target(target) is False


def test_stale_nyon_target_ignores_about_blank():
    target = {
        'type': 'page',
        'title': 'about:blank',
        'url': 'about:blank',
    }

    assert _is_stale_nyon_target(target) is False


def test_scrape_all_cleans_nyon_tabs_before_scraping(tmp_path, monkeypatch):
    import tools.scrape as scrape

    calls = []
    monkeypatch.setattr(scrape, 'STATUS_FILE', str(tmp_path / 'status.json'))

    class SourceQuery:
        def exclude(self, **kwargs):
            return self

        def __iter__(self):
            return iter([type('Source', (), {'slug': 'lcdh_nyon'})()])

    monkeypatch.setattr(scrape.PriceSource.objects, 'filter', lambda **kwargs: SourceQuery())
    monkeypatch.setattr(scrape, '_check_disk', lambda: 8)
    monkeypatch.setattr(scrape, '_cleanup_stale_nyon_tabs', lambda: calls.append('cleanup') or 2)
    monkeypatch.setattr(scrape, 'scrape_source', lambda slug: calls.append(f'scrape:{slug}') or {'created': 0, 'matched': 1, 'skipped': 1})

    results, errors = scrape.scrape_all()

    assert calls == ['cleanup', 'scrape:lcdh_nyon']
    assert results['lcdh_nyon']['matched'] == 1
    assert errors == 0


def test_scrape_all_excludes_requested_source(tmp_path, monkeypatch):
    import tools.scrape as scrape

    calls = []
    monkeypatch.setattr(scrape, 'STATUS_FILE', str(tmp_path / 'status.json'))

    class SourceQuery:
        def exclude(self, **kwargs):
            return self

        def __iter__(self):
            return iter([
                type('Source', (), {'slug': 'lcdh_nyon'})(),
                type('Source', (), {'slug': 'cigarone'})(),
            ])

    monkeypatch.setattr(scrape.PriceSource.objects, 'filter', lambda **kwargs: SourceQuery())
    monkeypatch.setattr(scrape, '_check_disk', lambda: 8)
    monkeypatch.setattr(scrape, '_cleanup_stale_nyon_tabs', lambda: calls.append('cleanup'))
    monkeypatch.setattr(scrape, 'scrape_source', lambda slug: calls.append(f'scrape:{slug}') or {'created': 0, 'matched': 1, 'skipped': 1})

    results, errors = scrape.scrape_all(exclude_sources={'lcdh_nyon'})

    assert calls == ['scrape:cigarone']
    assert 'lcdh_nyon' not in results
    assert results['cigarone']['matched'] == 1
    assert errors == 0


def test_write_scrape_status_records_single_source(tmp_path, monkeypatch):
    import json
    import tools.scrape as scrape

    status_file = tmp_path / 'status.json'
    monkeypatch.setattr(scrape, 'STATUS_FILE', str(status_file))

    scrape._write_scrape_status({
        'lcdh_nyon': {'created': 0, 'matched': 322, 'skipped': 336},
    })

    status = json.loads(status_file.read_text())
    assert status['lcdh_nyon']['success'] is True
    assert status['lcdh_nyon']['matched'] == 322
    assert status['lcdh_nyon']['skipped'] == 336
