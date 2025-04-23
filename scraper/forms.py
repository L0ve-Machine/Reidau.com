# scraper/forms.py

from django import forms
from .models import Video

class VideoUploadForm(forms.ModelForm):
    class Meta:
        model = Video
        fields = ['uploaded_file', 'alt_text']  # 必要に応じて他のフィールドも

    def clean_uploaded_file(self):
        f = self.cleaned_data.get('uploaded_file')
        if f:
            # 必要ならファイルサイズ/拡張子チェック
            if f.size > 50 * 1024 * 1024:  # 50MB 上限
                raise forms.ValidationError("ファイルは50MB以下でアップロードしてください。")
            if not f.content_type.startswith('video/'):
                raise forms.ValidationError("動画ファイルをアップロードしてください。")
        return f
