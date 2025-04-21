from django.urls import path
from . import views

urlpatterns = [
    path('',                      views.video_list,    name='video_list'),
    path('save/',                 views.save_view,     name='save'),
    path('ranking/',              views.video_ranking, name='video_ranking'),  # ← ここを '<str:disp_id>/' の前に
    path('<str:disp_id>/',        views.video_detail,  name='video_detail'),


    #admin系統は以下
    path('manage/videos/',           views.admin_video_list,   name='admin_video_list'),
    path('manage/videos/<int:pk>/toggle-delete/', views.admin_toggle_delete, name='admin_toggle_delete'),
    path('manage/videos/<int:pk>/toggle-ban-user/', views.admin_toggle_ban_user, name='admin_toggle_ban_user'),
    path('manage/videos/<int:pk>/toggle-pin/',    views.admin_toggle_pin,    name='admin_toggle_pin'),
    path('manage/videos/<int:pk>/set-pin-order/', views.admin_set_pin_order, name='admin_set_pin_order'),

]