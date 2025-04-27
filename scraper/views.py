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


def save_view(request):
    tweet_url = ""
    error = None

    if request.method == "POST" and request.POST.get("action") == "save":
        tweet_url = request.POST.get("param", "").strip()
        if not tweet_url:
            error = "URL を入力してください。"
            return render(request, "scraper/save.html", {"tweet_url": tweet_url, "error": error})

        # 1) yt_dlp で MP4 形式の動画 URL を取得
        try:
            ydl_opts = {
                "quiet": True,
                "skip_download": True,
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(tweet_url, download=False)
            formats = sorted(info.get("formats", []), key=lambda f: f.get("height", 0))
            video_url = formats[-1]["url"] if formats else info.get("url")
        except Exception as e:
            logger.exception("yt_dlp での情報抽出に失敗しました")
            error = "動画の抽出に失敗しました。URL を確認してください。"
            return render(request, "scraper/save.html", {"tweet_url": tweet_url, "error": error})

        # 2) ストリームを一時ファイルに保存
        try:
            resp = requests.get(video_url, stream=True)
            resp.raise_for_status()

            tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            for chunk in resp.iter_content(chunk_size=8192):
                tmp_video.write(chunk)
            tmp_video.flush()
            tmp_video.close()
        except Exception as e:
            logger.exception("動画のダウンロードに失敗しました")
            error = f"動画のダウンロードに失敗しました: {e}"
            return render(request, "scraper/save.html", {"tweet_url": tweet_url, "error": error})

        # 3) DB とファイル保存をトランザクション内で実行
        with transaction.atomic():
            disp_id = generate_unique_disp_id()
            user = request.user.username if request.user.is_authenticated else "anonymous"

            video = Video(
                disp_id=disp_id,
                user=user,
                redirect_url=tweet_url,
                tweet_url=tweet_url,
                alt_text="",
            )

            # 4) 一時動画ファイルを Video.uploaded_file に保存
            try:
                with open(tmp_video.name, 'rb') as f:
                    video.uploaded_file.save(f"{disp_id}.mp4", f, save=False)
            except Exception:
                logger.exception("動画ファイルの保存に失敗しました")
                raise

            # 5) サムネイル生成 (ffmpeg を利用、-y で既存ファイルを強制上書き)
            try:
                today = timezone.now().strftime("%Y/%m/%d")
                thumb_dir = os.path.join("thumbnails", today)
                if hasattr(default_storage, 'makedirs'):
                    default_storage.makedirs(thumb_dir)
                thumb_name = f"{disp_id}_thumb.jpg"
                thumb_tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name

                subprocess.run([
                    "ffmpeg", "-y", "-i", tmp_video.name,
                    "-vf", "thumbnail,scale=320:-1", "-frames:v", "1",
                    thumb_tmp
                ], check=True)

                with open(thumb_tmp, 'rb') as imgf:
                    thumb_path = os.path.join(thumb_dir, thumb_name)
                    default_storage.save(thumb_path, ContentFile(imgf.read()))
                    video.thumb_url = default_storage.url(thumb_path)
            except Exception as e:
                logger.warning(f"サムネイル生成に失敗しました: {e}")

            # 6) レコード保存
            video.save()

        messages.success(request, "動画を DB に保存しました。")

        # 7) 端末ダウンロード
        response = StreamingHttpResponse(
            open(tmp_video.name, 'rb'),
            content_type=resp.headers.get("Content-Type", "application/octet-stream")
        )
        response["Content-Disposition"] = f'attachment; filename="{disp_id}.mp4"'
        return response

    # GET またはエラー時はフォーム表示
    return render(request, "scraper/save.html", {"tweet_url": tweet_url, "error": error})



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