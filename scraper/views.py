from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from datetime import timedelta
from .models import Video
from .forms import VideoUploadForm
from django.db.models import Q
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
import yt_dlp
from .utils import generate_unique_disp_id
from django.http import StreamingHttpResponse, HttpResponseBadRequest
import io
import os
import requests
import imageio
from PIL import Image
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import logging
import tempfile
from django.db import transaction
import subprocess
from urllib.parse import urlparse, urlunparse
from django.conf import settings
from .twidropper import fetch_from_twidropper
from pathlib import Path


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
logger = logging.getLogger(__name__)
def video_list(request):
    q = request.GET.get('q', '').strip()

    # --- 1) ベースの QuerySet ---
    qs = Video.objects.order_by('-scraped_at')
    if q:
        qs = qs.filter(
            Q(disp_id__icontains=q) |
            Q(user__icontains=q) |
            Q(alt_text__icontains=q)
        )

    # --- 2) 20件ずつのページネーション ---
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    # --- 3) 今ページのオブジェクト ---
    videos_page = page_obj.object_list

    # --- 4) 5件ごとに広告を挿入 ---
    videos_with_ads = []
    for idx, video in enumerate(videos_page):
        videos_with_ads.append(video)
        if (idx + 1) % 5 == 0:
            videos_with_ads.append({
                'ad': True,
                'ad_content': '広告内容をここに挿入'
            })

    # --- 5) テンプレートに渡す ---
    return render(request, 'scraper/index.html', {
        'videos':   videos_with_ads,
        'page_obj': page_obj,
        'q':        q,
    })



def video_detail(request, disp_id):
    video = get_object_or_404(Video, disp_id=disp_id)
    # 表示回数をインクリメント
    video.view_count += 1
    video.save()

    return render(request, 'scraper/detail.html', {'video': video})


def normalize_twitter_url(url: str) -> str:
    """x.com / mobile.twitter.com → twitter.com に置き換え"""
    p = urlparse(url)
    host = p.netloc.lower()
    if host.endswith(("x.com", "mobile.twitter.com")):
        p = p._replace(netloc="twitter.com")
    return urlunparse(p)

def _download_with_ytdlp(url: str, cookie_path: Path | None) -> str:
    """
    url を mp4 にダウンロードし、実ファイルのパスを返す。
    20 KB 未満なら失敗として ValueError。
    """
    tmp_base = Path(tempfile.NamedTemporaryFile(delete=False).name)  # 拡張子無し
    outtmpl  = f"{tmp_base}.%(ext)s"                                 # 拡張子は yt-dlp

    ydl_opts = {
        "quiet": True,
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "http_headers": {"User-Agent": UA},
    }
    if cookie_path:
        ydl_opts["cookiefile"] = str(cookie_path)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # 実ファイル検出
    for ext in (".mp4", ".mkv", ".webm"):
        f = tmp_base.with_suffix(ext)
        if f.exists() and f.stat().st_size > 20 * 1024:   # 20 KB 以上
            return str(f)
    raise ValueError("yt-dlp の出力ファイルが見つからないか極端に小さい")

def save_view(request):
    tweet_url, error = "", None

    if request.method == "POST" and request.POST.get("action") == "save":
        tweet_url = request.POST.get("param", "").strip()
        if not tweet_url:
            return render(request, "scraper/save.html",
                          {"tweet_url": tweet_url, "error": "URL を入力してください。"})

        tweet_url = normalize_twitter_url(tweet_url)
        cookie_path = settings.COOKIES_FILE if settings.COOKIES_FILE.exists() else None

        # ① ツイート URL を直接 yt-dlp で DL
        try:
            tmp_path  = _download_with_ytdlp(tweet_url, cookie_path)
            video_src = tweet_url
        except Exception as e:
            logger.info(f"yt-dlp direct failed: {e}")
            tmp_path  = None

        # ② フォールバック: Twidropper → yt-dlp DL
        if tmp_path is None:
            video_src = fetch_from_twidropper(tweet_url)
            if not video_src:
                return render(request, "scraper/save.html",
                              {"tweet_url": tweet_url, "error": "動画の抽出に失敗しました。"})
            try:
                tmp_path = _download_with_ytdlp(video_src, None)   # 公開ツイのみ
            except Exception as e:
                logger.exception("動画のダウンロードに失敗しました")
                return render(request, "scraper/save.html",
                              {"tweet_url": tweet_url,
                               "error": f"動画のダウンロードに失敗しました: {e}"})

        # ③ DB 保存 + サムネイル生成
        with transaction.atomic():
            disp_id = generate_unique_disp_id()
            user = request.user.username if request.user.is_authenticated else "anonymous"

            video = Video(
                disp_id=disp_id,
                user=user,
                redirect_url=tweet_url,
                tweet_url=video_src,
                alt_text="",
            )
            with open(tmp_path, "rb") as f:
                video.uploaded_file.save(f"{disp_id}.mp4", f, save=False)

            # サムネイル
            try:
                today = timezone.now().strftime("%Y/%m/%d")
                thumb_dir = os.path.join("thumbnails", today)
                if hasattr(default_storage, "makedirs"):
                    default_storage.makedirs(thumb_dir)
                thumb_tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
                subprocess.run([
                    "ffmpeg", "-y", "-i", tmp_path,
                    "-vf", "thumbnail,scale=320:-1", "-frames:v", "1", thumb_tmp],
                    check=True)
                with open(thumb_tmp, "rb") as imgf:
                    thumb_path = os.path.join(thumb_dir, f"{disp_id}_thumb.jpg")
                    default_storage.save(thumb_path, ContentFile(imgf.read()))
                    video.thumb_url = default_storage.url(thumb_path)
            except Exception as e:
                logger.warning(f"サムネイル生成に失敗しました: {e}")

            video.save()

        messages.success(request, "動画を DB に保存しました。")

        return StreamingHttpResponse(
            open(tmp_path, "rb"),
            content_type="video/mp4",
            headers={"Content-Disposition": f'attachment; filename=\"{disp_id}.mp4\"'}
        )

    # GET またはエラー時
    return render(request, "scraper/save.html",
                  {"tweet_url": tweet_url, "error": error})



def get_ranked_videos(start_time):
    return Video.objects.filter(
        scraped_at__gte=start_time
    ).order_by('-view_count')

def video_ranking(request):
    # クエリパラメータで period を受け取る（'24h','1w','1m','1y'）
    period = request.GET.get('period', '24h')
    now = timezone.now()

    if period == '1w':
        start_time = now - timedelta(weeks=1)
        label = "1週間"
    elif period == '1m':
        start_time = now - timedelta(days=30)
        label = "1ヶ月"
    elif period == '1y':
        start_time = now - timedelta(days=365)
        label = "1年"
    else:
        # default '24h'
        start_time = now - timedelta(days=1)
        label = "24時間"

    ranking = get_ranked_videos(start_time)

    return render(request, 'scraper/ranking.html', {
        'ranking': ranking,
        'current_period': period,
        'period_label': label,
    })

def base_video_qs():
    return Video.objects.filter(
        is_deleted=False,
        is_banned_user=False,
    )


# --- get_ranked_videos の修正例 ---
def get_ranked_videos(start_time):
    qs = base_video_qs().filter(scraped_at__gte=start_time)
    # 固定表示：pin_order → その後 view_count
    pinned = qs.filter(is_pinned=True).order_by('pin_order','-view_count')
    others = qs.filter(is_pinned=False).order_by('-view_count')
    # リスト結合してレンダリング用に
    return list(pinned) + list(others)

# --- video_ranking の修正例（管理画面保護） ---

def video_ranking(request):
    # ① period の取得
    period = request.GET.get('period', '24h')
    now = timezone.now()
    if period == '1w':
        start_time = now - timedelta(weeks=1)
        label = "1週間"
    elif period == '1m':
        start_time = now - timedelta(days=30)
        label = "1ヶ月"
    elif period == '1y':
        start_time = now - timedelta(days=365)
        label = "1年"
    else:
        start_time = now - timedelta(days=1)
        label = "24時間"

    # ② 全ランキング取得
    ranking_qs = get_ranked_videos(start_time)

    # ← ここで最大400件に制限（20ページ×20件）
    max_pages = 10
    per_page  = 20
    ranking_qs = ranking_qs[: max_pages * per_page ]

    # ③ ページネーション
    paginator = Paginator(ranking_qs, per_page)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # ④ 今ページのアイテム
    ranking_page = page_obj.object_list

    # ⑤ テンプレートへ
    return render(request, 'scraper/ranking.html', {
        'ranking':        ranking_page,
        'page_obj':       page_obj,
        'current_period': period,
        'period_label':   label,
    })

def upload_view(request):
    if request.method == 'POST':
        form = VideoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            video = form.save(commit=False)
            video.disp_id = generate_unique_disp_id()  # ここでユニークIDを取得
            video.user    = request.user.username if request.user.is_authenticated else 'anonymous'
            video.save()
            messages.success(request, "アップロードが完了しました。")
            return redirect('video_detail', disp_id=video.disp_id)
    else:
        form = VideoUploadForm()

    return render(request, 'scraper/upload.html', {'form': form})


def download_view(request):
    video_url = request.GET.get("url")
    if not video_url:
        return HttpResponseBadRequest("動画 URL が指定されていません。")

    resp = requests.get(video_url, stream=True)
    if resp.status_code != 200:
        return HttpResponseBadRequest("動画を取得できませんでした。")

    response = StreamingHttpResponse(
        resp.iter_content(chunk_size=8192),
        content_type=resp.headers.get("Content-Type", "application/octet-stream")
    )
    response["Content-Disposition"] = 'attachment; filename="twitter_video.mp4"'
    return response

@staff_member_required
def admin_video_list(request):
    videos = Video.objects.order_by('-scraped_at')
    return render(request, 'scraper/admin_video_list.html', {
        'videos': videos,
    })

@staff_member_required
def admin_toggle_delete(request, pk):
    video = get_object_or_404(Video, pk=pk)
    video.is_deleted = not video.is_deleted
    video.save()
    return redirect('admin_video_list')

@staff_member_required
def admin_toggle_ban_user(request, pk):
    video = get_object_or_404(Video, pk=pk)
    # 当該ユーザーの動画すべてに適用
    Video.objects.filter(user=video.user).update(is_banned_user=not video.is_banned_user)
    return redirect('admin_video_list')

@staff_member_required
def admin_toggle_pin(request, pk):
    video = get_object_or_404(Video, pk=pk)
    video.is_pinned = not video.is_pinned
    if not video.is_pinned:
        video.pin_order = None
    else:
        # 固定時に最大の既存 order +1 を設定（末尾に）
        max_order = Video.objects.filter(is_pinned=True).aggregate(models.Max('pin_order'))['pin_order__max'] or 0
        video.pin_order = max_order + 1
    video.save()
    return redirect('admin_video_list')

@staff_member_required
def admin_set_pin_order(request, pk):
    video = get_object_or_404(Video, pk=pk)
    if request.method == 'POST':
        try:
            order = int(request.POST.get('pin_order'))
        except (TypeError, ValueError):
            order = None
        video.pin_order = order
        video.save()
    return redirect('admin_video_list')