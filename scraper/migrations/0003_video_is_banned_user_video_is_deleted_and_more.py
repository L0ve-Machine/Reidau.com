# Generated by Django 5.1.4 on 2025-04-21 20:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scraper', '0002_video_view_count'),
    ]

    operations = [
        migrations.AddField(
            model_name='video',
            name='is_banned_user',
            field=models.BooleanField(default=False, help_text='指定ユーザーの動画を禁止'),
        ),
        migrations.AddField(
            model_name='video',
            name='is_deleted',
            field=models.BooleanField(default=False, help_text='管理者が非表示にした動画'),
        ),
        migrations.AddField(
            model_name='video',
            name='is_pinned',
            field=models.BooleanField(default=False, help_text='ランキングで上位に固定表示'),
        ),
        migrations.AddField(
            model_name='video',
            name='pin_order',
            field=models.PositiveIntegerField(blank=True, help_text='固定表示の優先度、数値が小さいほど上位', null=True),
        ),
    ]
