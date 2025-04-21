from django.contrib import admin
from django.urls import path, include
from scraper.views import save_view

urlpatterns = [
    path('admin/',   admin.site.urls),

    # 保存フォームだけは /save/
    path('save/',    save_view,        name='save'),

    # ↓ これを追加 ↓
    # ルート (“http://.../”) にも scraper.urls を当てる
    path('',         include('scraper.urls')),

    # （既にある）/videos/ 以下にも当てたいなら残して OK
    # path('videos/',  include('scraper.urls')),
]

