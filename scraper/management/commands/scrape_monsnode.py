# scraper/management/commands/scrape_monsnode.py
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from scraper.models import Video

class Command(BaseCommand):
    help = 'Scrape monsnode.com and save only new videos'

    def handle(self, *args, **options):
        base_url = 'https://monsnode.com/'
        existing_ids = set(Video.objects.values_list('disp_id', flat=True))
        page = 0

        while True:
            url = base_url if page == 0 else f"{base_url}?page={page}"
            resp = requests.get(url)
            if resp.status_code != 200:
                self.stdout.write(self.style.ERROR(f'Failed to fetch page {page}: {resp.status_code}'))
                break

            soup  = BeautifulSoup(resp.text, 'html.parser')
            items = soup.find_all('div', class_='listn')
            if not items:
                break

            new_found = False
            for item in items:
                disp_id = item['id']
                if disp_id in existing_ids:
                    continue

                href = item.find('a', rel='nofollow')['href']
                redirect_url = href if href.startswith('http') else requests.compat.urljoin(base_url, href)
                img  = item.find('img')
                thumb = img['src']
                alt   = img.get('alt', '')
                user  = item.find('div', class_='user').get_text(strip=True)

                Video.objects.create(
                    disp_id=disp_id,
                    user=user,
                    redirect_url=redirect_url,
                    thumb_url=thumb,
                    alt_text=alt,
                )
                existing_ids.add(disp_id)
                new_found = True
                self.stdout.write(self.style.SUCCESS(f'Created: {disp_id}'))

            if not new_found:
                # このページで新規がなければ以降も新規は出ないと判断して終了
                break
            page += 1

        self.stdout.write(self.style.SUCCESS('Scraping done.'))