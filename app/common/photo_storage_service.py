# app/services/photo_storage_service.py

from __future__ import annotations

from typing import BinaryIO
from uuid import uuid4

import boto3


class PhotoStorageService:
    """Amazon S3上の画像ファイルを管理するサービス。"""

    MIMETYPES = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }

    # S3クライアントの初期化
    def __init__(
        self,
        bucket_name: str,
        region_name: str = "ap-northeast-1",
    ):
        self.bucket_name = bucket_name

        self.s3 = boto3.client(
            "s3",
            region_name=region_name,
        )

    # 画像のアップロード
    def save_photo(
        self,
        file: BinaryIO,
        filename: str,
    ) -> str:
        """画像をS3に保存し、オブジェクトキーを返す。"""

        extension = "." + filename.rsplit(".", 1)[-1].lower()

        if extension not in self.MIMETYPES:
            raise ValueError("対応していない画像形式です。")

        key = f"photos/{uuid4().hex}{extension}"

        self.s3.upload_fileobj(
            Fileobj=file,
            Bucket=self.bucket_name,
            Key=key,
            ExtraArgs={
                "ContentType": self.MIMETYPES[extension],
            },
        )

        return key

    # 画像データの取得
    def read_photo(self, key: str) -> bytes:
        """S3から画像データを取得する。"""

        response = self.s3.get_object(
            Bucket=self.bucket_name,
            Key=key,
        )

        body = response["Body"]

        try:
            return body.read()
        finally:
            body.close()

    # 画像の削除
    def delete_photo(self, key: str) -> None:
        """S3から画像を削除する。"""

        self.s3.delete_object(
            Bucket=self.bucket_name,
            Key=key,
        )

    # 署名付きURLの発行
    def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 300,
    ) -> str:
        """画像取得用の署名付きURLを発行する。"""

        return self.s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": key,
            },
            ExpiresIn=expires_in,
        )
