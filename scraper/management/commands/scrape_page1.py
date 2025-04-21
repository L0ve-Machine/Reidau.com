import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from scraper.models import Video

class Command(BaseCommand):
    help = 'Scrape first page of monsnode.com and save video info'

    def handle(self, *args, **options):
        url = 'https://monsnode.com/'
        resp = requests.get(url)
        if resp.status_code != 200:
            self.stdout.write(self.style.ERROR(f'Failed to fetch: {resp.status_code}'))
            return

        soup = BeautifulSoup(resp.text, 'html.parser')
        items = soup.find_all('div', class_='listn')

        for item in items:
            disp_id = item['id']
            link    = item.find('a', rel='nofollow')['href']
            full_url = link if link.startswith('http') else requests.compat.urljoin(url, link)
            img     = item.find('img')
            thumb   = img['src']
            alt     = img.get('alt','')
            user    = item.find('div', class_='user').get_text(strip=True)

            obj, created = Video.objects.update_or_create(
                disp_id=disp_id,
                defaults={
                    'user': user,
                    'redirect_url': full_url,
                    'thumb_url': thumb,
                    'alt_text': alt,
                }
            )
            verb = 'Created' if created else 'Updated'
            self.stdout.write(f'{verb}: {disp_id}')