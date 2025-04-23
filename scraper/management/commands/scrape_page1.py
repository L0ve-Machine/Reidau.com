# scraper/management/commands/scrape_page1.py

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from scraper.models import Video

class Command(BaseCommand):
    help = 'Scrape container page and save video info including tweet_url'

    def handle(self, *args, **options):
        url = 'https://monsnode.com/'
        resp = requests.get(url)
        if resp.status_code != 200:
            self.stderr.write(f'Failed to fetch: {resp.status_code}')
            return

        soup = BeautifulSoup(resp.text, 'html.parser')
        container = soup.find('div', id='container')
        if not container:
            self.stderr.write('Container not found')
            return

        items = container.find_all('div', class_='item')
        for item in items:
            # direct video link
            trigger = item.find('a', class_='trigger')
            if not trigger or not trigger.get('href'):
                continue
            video_url = trigger['href'].strip()

            # thumbnail (unused)
            thumb = trigger.find('img')
            thumb_url = thumb['src'].strip() if thumb and thumb.get('src') else ''

            # tweet link
            tweet_url = ''
            saisei = item.find('div', class_='saisei')
            if saisei:
                a = saisei.find('a')
                if a and a.get('href'):
                    tweet_url = a['href'].strip()

            # use tweet ID as disp_id
            disp_id = tweet_url.rstrip('/').split('/')[-1] if tweet_url else video_url

            obj, created = Video.objects.update_or_create(
                disp_id=disp_id,
                defaults={
                    'redirect_url': video_url,
                    'thumb_url':    thumb_url,
                    'alt_text':     '',
                    'tweet_url':    tweet_url,    # ← ここ必ず入れる
                    'user':         '',           # もし不要なら削除可
                }
            )
            self.stdout.write(f'{"Created" if created else "Updated"}: {disp_id}')
