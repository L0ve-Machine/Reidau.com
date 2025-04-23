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
import requests



def video_list(request):
    q = request.GET.get('q', '').strip()
    videos = Video.objects.order_by('-scraped_at')

    if q:
        # disp_id, user, alt_text に部分一致検索
        videos = videos.filter(
            Q(disp_id__icontains=q) |
            Q(user__icontains=q) |
            Q(alt_text__icontains=q)
        )

    # 広告を挿入するロジック
    videos_with_ads = []
    for index, video in enumerate(videos):
        videos_with_ads.append(video)
        if (index + 1) % 5 == 0:  # 5番目の動画の後に広告を挿入
            # 広告内容を適宜変更
            videos_with_ads.append({'ad': True, 'ad_content': '広告内容をここに挿入'})

    return render(request, 'scraper/index.html', {
        'videos': videos_with_ads,
        'q': q,
    })


def video_detail(request, disp_id):
    video = get_object_or_404(Video, disp_id=disp_id)
    # 表示回数をインクリメント
    video.view_count += 1
    video.save()

    return render(request, 'scraper/detail.html', {'video': video})


def save_view(request):
    video_url = None
    tweet_url = ""
    error     = None

    if request.method == "POST":
        tweet_url = request.POST.get("param", "").strip()
        if tweet_url:
            try:
                ydl_opts = {
                    "quiet": True,
                    "skip_download": True,
                    "force_generic_extractor": True,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(tweet_url, download=False)
                    if "formats" in info:
                        video_url = info["formats"][-1]["url"]
                    else:
                        video_url = info.get("url")
            except Exception:
                error = "動画の抽出に失敗しました。URL を確認してください。"

    return render(request, "scraper/save.html", {
        "video_url": video_url,
        "tweet_url": tweet_url,
        "error": error,
    })

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

# --- video_list の修正例 ---
def video_list(request):
    q = request.GET.get('q','').strip()
    qs = base_video_qs().order_by('-scraped_at')
    if q:
        qs = qs.filter(
            Q(disp_id__icontains=q) |
            Q(user__icontains=q) |
            Q(alt_text__icontains=q)
        )
    # （広告挿入ロジックはそのまま）
    # videos_with_ads = …

    return render(request,'scraper/index.html',{
        'videos': qs,  # or videos_with_ads
        'q': q,
    })

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
    period = request.GET.get('period','24h')
    now = timezone.now()
    if period=='1w':
        start=now-timedelta(weeks=1)
    elif period=='1m':
        start=now-timedelta(days=30)
    elif period=='1y':
        start=now-timedelta(days=365)
    else:
        start=now-timedelta(days=1)
    ranking = get_ranked_videos(start)
    return render(request,'scraper/ranking.html',{
        'ranking': ranking,
        'current_period': period,
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