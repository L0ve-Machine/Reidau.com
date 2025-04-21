# scraper/admin.py
from django.contrib import admin
from .models import Video


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('disp_id', 'user', 'view_count', 'is_deleted', 'is_banned_user', 'is_pinned', 'pin_order')
    list_filter = ('is_deleted', 'is_banned_user', 'is_pinned')
    search_fields = ('disp_id', 'user', 'alt_text')
    ordering = ('-scraped_at',)
    actions = ['mark_deleted', 'unmark_deleted', 'ban_user', 'unban_user', 'pin_video', 'unpin_video']

    @admin.action(description="選択動画を非表示にする")
    def mark_deleted(self, request, queryset):
        queryset.update(is_deleted=True)

    @admin.action(description="選択動画の非表示を解除する")
    def unmark_deleted(self, request, queryset):
        queryset.update(is_deleted=False)

    @admin.action(description="選択ユーザーの動画を禁止する")
    def ban_user(self, request, queryset):
        users = queryset.values_list('user', flat=True).distinct()
        Video.objects.filter(user__in=users).update(is_banned_user=True)

    @admin.action(description="選択ユーザーの禁止を解除する")
    def unban_user(self, request, queryset):
        users = queryset.values_list('user', flat=True).distinct()
        Video.objects.filter(user__in=users).update(is_banned_user=False)

    @admin.action(description="選択動画を固定表示にする")
    def pin_video(self, request, queryset):
        # pin_order をずらすなど工夫できますが、ここでは一律 0 に
        queryset.update(is_pinned=True, pin_order=0)

    @admin.action(description="選択動画の固定表示を解除する")
    def unpin_video(self, request, queryset):
        queryset.update(is_pinned=False, pin_order=None)

