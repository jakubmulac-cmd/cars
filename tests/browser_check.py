"""End-to-end checks on a temporary copy, never on the user's database.

Uses an optional system Playwright/Chromium installation. Run from the checkout:
  python3 tests/browser_check.py --data-dir /private/path --output /private/results
"""
import argparse
import json
import os
import secrets
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix='cars-browser-') as temp:
        with sqlite3.connect(args.data_dir / 'fleet.sqlite3') as source, sqlite3.connect(Path(temp) / 'fleet.sqlite3') as target:
            source.backup(target)
            target.execute('DELETE FROM users')
            target.execute('DELETE FROM sessions')
            target.commit()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port = sock.getsockname()[1]
        origin = f'http://127.0.0.1:{port}'
        process = subprocess.Popen([str(root / '.venv/bin/python'),'-m','uvicorn','fleet.main:app','--host','127.0.0.1','--port',str(port),'--no-proxy-headers','--no-access-log'],cwd=root,env={**os.environ,'FLEET_DATA_DIR':temp},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for attempt in range(50):
                try:
                    with urllib.request.urlopen(origin + '/api/health', timeout=1) as response:
                        assert response.status == 200
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('Test server did not start')
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                context = browser.new_context(viewport={'width':1440,'height':1100})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(origin)
                page.locator('#auth-screen').wait_for(state='visible')
                page.screenshot(path=str(args.output / 'login-desktop.png'),full_page=True)
                page.locator('#password').fill(secrets.token_urlsafe(24))
                page.locator('#auth-submit').click()
                page.locator('#application').wait_for(state='visible')
                assert page.locator('#nav-vehicles').inner_text() == '31'
                assert page.locator('#nav-issues').inner_text() == '38'
                page.screenshot(path=str(args.output / 'overview-desktop.png'),full_page=True)
                page.get_by_role('link', name='Vozidla', exact=False).first.click()
                page.locator('#vehicle-search').wait_for()
                assert page.locator('#vehicle-list tr').count() == 31
                page.locator('#vehicle-search').fill('Golf')
                assert page.locator('#vehicle-list tr.vehicle-row').count() == 1
                page.locator('#vehicle-list button').click()
                page.locator('#details').wait_for(state='visible')
                assert 'V007' in page.locator('#detail-content').inner_text()
                for name in ('Pojištění','Historie','Podklady','Přehled'):
                    page.get_by_role('tab',name=name,exact=True).click()
                page.locator('[data-action="reading"]').first.click()
                page.locator('#reading-form [name="km"]').fill('52000')
                page.locator('#reading-form [name="evidence"]').fill('Fotografie tachometru — ověřovací test na kopii databáze')
                page.locator('#reading-form button[type="submit"]').click()
                page.locator('#action-dialog').wait_for(state='hidden')
                page.get_by_text('Odečet byl uložen.',exact=True).wait_for()
                page.get_by_role('tab',name='Historie',exact=True).click()
                assert '52\xa0000' in page.locator('#detail-content').inner_text()
                page.locator('[data-action="close-details"]').click()
                page.get_by_role('link',name='Úkoly',exact=False).first.click()
                page.locator('#priority-filter').select_option('P0')
                assert page.locator('.task-card').count() >= 1
                page.locator('.task-card button').first.click()
                page.locator('#task-form [name="assigned_to"]').fill('Správce vozového parku')
                page.locator('#task-form button[type="submit"]').click()
                page.locator('#action-dialog').wait_for(state='hidden')
                page.get_by_text('Úkol byl uložen.',exact=True).wait_for()
                assert 'Správce vozového parku' in page.locator('#task-list').inner_text()
                page.get_by_role('link',name='Pojištění',exact=True).click()
                page.get_by_text('53 847 Kč',exact=True).wait_for()
                assert '106\xa0230 Kč' in page.locator('#page-content').inner_text()
                page.get_by_role('link',name='Podklady',exact=True).click()
                page.locator('.source-card').first.wait_for()
                assert page.locator('.source-card').count() == 21
                page.get_by_role('link',name='Připojení a data',exact=True).click()
                page.locator('#connectors .connector-row').first.wait_for()
                assert page.locator('#connectors .connector-row').count() == 3
                seed = args.data_dir / 'import/fleet_context_2026-10-11.json'
                # Reverse proxies may return HTML or plain text instead of JSON.
                # The import screen must explain the failure and remain usable.
                page.route('**/api/imports/preview', lambda route: route.fulfill(status=413,content_type='text/html',body='<html>proxy-only private content</html>'))
                page.locator('#import-file').set_input_files(str(seed))
                page.get_by_text('HTTP 413',exact=False).wait_for()
                assert 'proxy-only private content' not in page.locator('#page-content').inner_text()
                assert page.locator('[data-action="commit-import"]').count() == 0
                page.unroute('**/api/imports/preview')
                page.locator('#import-file').set_input_files([])
                page.route('**/api/imports/preview', lambda route: route.fulfill(status=500,content_type='text/plain',body='private traceback'))
                page.locator('#import-file').set_input_files(str(seed))
                page.get_by_text('HTTP 500',exact=False).wait_for()
                assert 'private traceback' not in page.locator('#page-content').inner_text()
                page.unroute('**/api/imports/preview')
                page.locator('#import-file').set_input_files([])
                page.locator('#import-file').set_input_files(str(seed))
                page.get_by_text('Validace prošla',exact=False).wait_for()
                page.locator('[data-action="commit-import"]').click()
                page.get_by_text('Import dokončen bez duplicit.',exact=True).wait_for()
                assert page.locator('#nav-vehicles').inner_text() == '31'
                with page.expect_download() as download:
                    page.locator('[data-action="export"]').click()
                export_path = download.value.path()
                exported = json.loads(Path(export_path).read_text())
                assert len(exported['vehicles']) == 31
                assert len(exported['source_observations']) == 2885
                page.get_by_role('link',name='Přehled',exact=True).click()
                page.set_viewport_size({'width':390,'height':844})
                page.locator('#toast').wait_for(state='hidden')
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.screenshot(path=str(args.output / 'overview-mobile.png'),full_page=True)
                page.get_by_role('link',name='Vozidla',exact=False).first.click()
                page.locator('#vehicle-search').fill('Porsche')
                assert page.locator('#vehicle-list tr.vehicle-row').count() >= 1
                page.locator('#vehicle-list button').first.click()
                page.locator('#details').wait_for(state='visible')
                assert page.locator('#details').is_visible()
                page.screenshot(path=str(args.output / 'detail-mobile.png'),full_page=True)
                page.locator('[data-action="close-details"]').click()
                page.locator('#logout').click()
                page.locator('#auth-screen').wait_for(state='visible')
                assert not page.locator('#application').is_visible()
                assert not errors, '\n'.join(errors)
                browser.close()
                print('Browser checks passed: authentication, 31 records, search, four detail tabs, manual reading, task assignment, insurance sums, 21 sources, disabled connectors, clear proxy/server import errors and successful retry, repeat import, export, mobile layout, logout; no JavaScript errors.')
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == '__main__':
    main()
