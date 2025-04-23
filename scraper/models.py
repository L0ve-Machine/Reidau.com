# scraper/models.py

from django.db import models

class Video(models.Model):
    disp_id        = models.CharField(max_length=32, unique=True)
    user           = models.CharField(max_length=64)
    redirect_url   = models.URLField()
    thumb_url      = models.URLField()
    alt_text       = models.TextField(blank=True)
    tweet_url      = models.URLField(blank=True)
    scraped_at     = models.DateTimeField(auto_now=True)
    view_count     = models.IntegerField(default=0)
    is_deleted     = models.BooleanField(default=False)
    is_banned_user = models.BooleanField(default=False)
    is_pinned      = models.BooleanField(default=False)
    pin_order      = models.PositiveIntegerField(null=True, blank=True)

    # ここを追加
    uploaded_file  = models.FileField(
        upload_to='videos/%Y/%m/%d/',
        blank=True,
        null=True,
        help_text="ユーザーがアップロードした動画ファイル"
    )

    def __str__(self):
        return f"{self.user} – {self.disp_id}"
