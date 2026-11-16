# Modelの組み込み

26_テーブル設計書(2).xlsx（2026年11月13日改訂）の14テーブルに対応しています。
このフォルダを既存プロジェクトの app/models/ に配置してください。
既存の app/extensions.py に定義された db を共有します。この成果物には
extensions.py やアプリ本体を含めていません。

## アプリ起動時の読み込み

既存の app/__init__.py の create_app() 内で、db.init_app(app) の後に
次の1行を追加してください。既に同じ読み込みがある場合は追加不要です。

```python
from app import models
```

Modelを読み込むことで、Flask-Migrateが全テーブルを検出できるようになります。
Modelファイル内で新たにSQLAlchemyインスタンスを作らないでください。

## 実装上の扱い

- 物理テーブル名・カラム名・型・文字数・PK・FK・NULL可否は設計書に対応。
- user_auth は provider_code と provider_user_id の複合主キー。
- マスタのコードは自動採番せず、設計書で自動採番とされたIDのみ自動採番。
- user.role_code の初期値は1。マスタデータは別途登録が必要です。
- damage_report の3つのステータス参照は foreign_keys を明示して区別。
- damage_location.severity の NULL（未分析）と0（判定不能）は区別。
- 各関係は双方向の relationship と back_populates で定義。
- 設計書にない削除連鎖や1対1制約は追加していません。
- メール認証（provider_code=0）の空でないpassword_hash、および分析の
  damage_level（1〜5）は備考に基づき名前付きCHECK制約を設定。
  MySQLでCHECKを実際に強制するには8.0.16以降が必要です。
- created_at と updated_at の初期値はDBのCURRENT_TIMESTAMP。
  updated_at の自動更新はDBのCURRENT_TIMESTAMP。
  日時はDB接続のタイムゾーンに従うため、接続設定を統一してください。
- 被害箇所・写真の最低1件という件数条件は外部キーだけでは保証できません。
  登録処理側でトランザクションと入力検証を実装してください。

## 既存アプリでの確認

Flask-SQLAlchemy等の既存の依存関係を用意したうえで、Modelの読み込み、
マイグレーション生成、生成内容のレビュー、テストDBへの適用を行ってください。
既にマイグレーション管理を開始している場合、db init の再実行は不要です。

```powershell
python -m flask --app app:create_app db migrate -m "Add initial models"
python -m flask --app app:create_app db upgrade
```

この成果物の作成時にはDB操作は行っていません。構文・設計書との定義照合・
関連付けの静的チェックを実施しました。Flask-SQLAlchemyが検証環境に
未導入のため、ORMの実行検証とMySQLへの適用検証は未実施です。
