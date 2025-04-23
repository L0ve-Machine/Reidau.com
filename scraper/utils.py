# scraper/utils.py
import uuid
from .models import Video

def generate_unique_disp_id():
    """
    UUID4 の 32 文字 hex 文字列を生成し、
    既存の Video.disp_id と重複しなければ返す。
    重複時は再試行。
    """
    while True:
        disp_id = uuid.uuid4().hex
        if not Video.objects.filter(disp_id=disp_id).exists():
            return disp_id
