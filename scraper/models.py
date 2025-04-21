from django.db import models


class Video(models.Model):
    disp_id = models.CharField(max_length=32, unique=True)
    user = models.CharField(max_length=64)
    redirect_url = models.URLField()
    thumb_url = models.URLField()
    alt_text = models.TextField(blank=True)
    scraped_at = models.DateTimeField(auto_now=True)
    view_count = models.IntegerField(default=0)

    # 追加フィールド
    is_deleted = models.BooleanField(default=False, help_text="管理者が非表示にした動画")
    is_banned_user = models.BooleanField(default=False, help_text="指定ユーザーの動画を禁止")
    is_pinned = models.BooleanField(default=False, help_text="ランキングで上位に固定表示")
    pin_order = models.PositiveIntegerField(null=True, blank=True, help_text="固定表示の優先度、数値が小さいほど上位")

    def __str__(self):
        return f"{self.user} – {self.disp_id}"