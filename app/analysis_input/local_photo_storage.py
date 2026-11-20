# app/analysis_input/local_photo_storage.py
"""写真のローカル保存(開発用)。

S3の PhotoStorageService ができるまでの代わりに、サーバー上のフォルダ
(instance/uploads/)へ写真を保存する。views.py の _store_photos() は
app.extensions["photo_storage_service"] を呼ぶので、このクラスを登録すれば動く。

DBの damage_photo.s3_object_key には、S3のキーと同じ形("photos/user_1/xxxx.jpg")を保存する。
後でS3に移すときは、uploads フォルダの中身を同じキーでバケットにアップロードすれば、
DBの値を書き換えずに済む。
"""
from __future__ import annotations

import uuid
from pathlib import Path


class PhotoStorageError(Exception):
    """写真の保存・取得に失敗した。"""


# ファイルの先頭バイトで形式を判定する(ファイル名や拡張子は信用しない)
def _detect_extension(header: bytes) -> str | None:
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header[0:4] == b"RIFF" and header[8:12] == b"WEBP":
        return ".webp"
    return None


class LocalPhotoStorage:
    def __init__(self, base_dir) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def upload_photo(self, file_storage, *, user_id=None) -> str:
        """アップロードされた写真を保存し、キー("photos/...")を返す。
        file_storage: Flask(Werkzeug)の FileStorage"""
        header = file_storage.stream.read(12)
        file_storage.stream.seek(0)

        extension = _detect_extension(header)
        if extension is None:
            raise PhotoStorageError("対応していない画像形式です(JPEG・PNG・WEBPのみ)。")

        # 保存名は利用者のファイル名を使わず、ランダムな名前にする
        owner = "guest" if user_id is None else f"user_{''.join(c for c in str(user_id) if c.isalnum())}"
        key = f"photos/{owner}/{uuid.uuid4().hex}{extension}"

        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_storage.save(path)
        return key

    def read_photo(self, key: str) -> bytes:
        """キーの写真のバイト列を返す(AI分析に渡すときなどに使う)。"""
        path = self._path_for(key)
        if not path.is_file():
            raise PhotoStorageError("写真が見つかりません。")
        return path.read_bytes()

    def delete_photo(self, key: str) -> None:
        """キーの写真を削除する(なければ何もしない)。"""
        self._path_for(key).unlink(missing_ok=True)

    def _path_for(self, key: str) -> Path:
        """キー → ファイルの場所。uploads フォルダの外を指すキーは拒否する。"""
        path = (self.base_dir / key).resolve()
        if self.base_dir not in path.parents:
            raise PhotoStorageError("不正な写真キーです。")
        return path
