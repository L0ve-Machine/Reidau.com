import cloudscraper
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from urllib.parse import urlparse
from scraper.models import Video

class Command(BaseCommand):
    help = 'Infinite-scroll scrape + skip duplicates in one run'

    def handle(self, *args, **options):
        base_url = 'https://www.twidouga.net/jp/realtime_t1.php'
        page_tpl = base_url + '?page={}'
        scraper = cloudscraper.create_scraper(
            browser={'browser':'chrome','platform':'windows','mobile':False}
        )

        all_items = []
        # 1ページ目
        resp = scraper.get(base_url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        container = soup.find('div', id='container')
        if container:
            all_items.extend(container.find_all('div', class_='item'))

        # ページ 2～MAX を取得
        MAX_PAGES = 20
        for page in range(2, MAX_PAGES+1):
            resp = scraper.get(page_tpl.format(page), timeout=10)
            if resp.status_code != 200:
                break
            soup = BeautifulSoup(resp.text, 'html.parser')
            items = soup.find_all('div', class_='item')
            if not items:
                break
            all_items.extend(items)

        self.stdout.write(f'Total raw items: {len(all_items)}')

        seen = set()
        created, updated = 0, 0

        for idx, item in enumerate(all_items, start=1):
            # — disp_id を決定 —
            # 元ツイート URL があればそちらの ID、なければ動画 URL をそのまま
            tweet_link = item.find('div', class_='saisei')
            if tweet_link and tweet_link.a:
                disp_id = tweet_link.a['href'].rstrip('/').split('/')[-1]
            else:
                # 動画 URL を探して取ってくる（.mp4?tag=… でもマッチ）
                video_href = ''
                for a in item.find_all('a'):
                    href = a.get('href','').strip()
                    if 'video.twimg.com' in href and '.mp4' in href:
                        video_href = href
                        break
                disp_id = video_href

            # ―― すでに出現済みならスキップ ――
            if not disp_id or disp_id in seen:
                continue
            seen.add(disp_id)

            # ―― 以降は元の保存ロジックをそのまま ――
            # video_url, thumb_url, tweet_url を抽出
            video_url = ''
            for a in item.find_all('a'):
                href = a.get('href','').strip()
                if 'video.twimg.com' in href and '.mp4' in href:
                    video_url = href
                    break
            if not video_url:
                continue

            thumb_url = ''
            img = item.find('img')
            if img and img.get('src'):
                thumb_url = img['src'].strip()

            tweet_url = ''
            saisei = item.find('div', class_='saisei')
            if saisei and saisei.a:
                tweet_url = saisei.a['href'].strip()

            obj, was_created = Video.objects.update_or_create(
                disp_id=disp_id,
                defaults={
                    'redirect_url': video_url,
                    'thumb_url':    thumb_url,
                    'alt_text':     '',
                    'tweet_url':    tweet_url,
                    'user':         '',
                }
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done. Created: {created}, Updated: {updated}'
        ))
