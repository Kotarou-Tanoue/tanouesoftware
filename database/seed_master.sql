-- MySQL 8.4 / UTF-8
-- 出典: 26_テーブル設計書.xlsx（各マスタ定義書の備考欄）
-- 作成日: 2026-11-17
-- 前提: Flask-Migrate適用済み。設計書どおりの主キー、InnoDBを使用すること。
-- 実行前に対象DBを選択すること。DB名は設計書に未記載のため固定しない。
-- 例: mysql --default-character-set=utf8mb4 --database=対象DB -u ユーザー -p < seed_master.sql
-- 専用接続で実行し、エラー時は停止すること（--force は使用しない）。
-- GUIではエラー後の実行を停止し、同一接続で ROLLBACK; を実行すること。
-- START TRANSACTIONは既存トランザクションを暗黙コミットするため、作業中の接続では実行しない。
--
-- 再実行: 同一主キーは名称のみ設計書の値に更新。主キー変更・削除はしない。
-- 設計書にない既存行は残す。REPLACE / TRUNCATE / DELETE は使用しない。
-- 外部キー検査を無効化しない。6マスタ間に外部キー依存はなく、子テーブルより先に実行する。
--
-- 未記載事項:
-- ・6マスタの「初期値」欄は空欄。以下は備考欄のコード・名称一覧を初期登録する。
-- ・role_nameは名称欄の admin/user を採用（コード欄の管理者/利用者は説明）。
-- ・provider_nameはprovider_code備考の email/LINE を採用。その他の方式は未定義。
-- ・追加コード、表示順、作成日時等は未記載のため補完しない。
-- ・location_severityに「未分析」行は作らない。
--   被害箇所定義書 AK12: NULL＝未分析、0＝分析したが判定不能。

SET NAMES utf8mb4;
START TRANSACTION;

-- テーブル定義書_権限テーブル AK5: 0.管理者、1.利用者 / AK6: 0.admin、1.user
INSERT INTO `role` (`role_code`, `role_name`)
VALUES (0, 'admin'), (1, 'user') AS seed_row
ON DUPLICATE KEY UPDATE `role_name` = seed_row.`role_name`;

-- テーブル定義書_認証方式テーブル AK5: 0.email、1.LINE
INSERT INTO `provider` (`provider_code`, `provider_name`)
VALUES (0, 'email'), (1, 'LINE') AS seed_row
ON DUPLICATE KEY UPDATE `provider_name` = seed_row.`provider_name`;

-- テーブル定義書_建物種別テーブル AK5: 1.戸建て、2.集合住宅
INSERT INTO `building_type` (`type_code`, `type_name`)
VALUES (1, '戸建て'), (2, '集合住宅') AS seed_row
ON DUPLICATE KEY UPDATE `type_name` = seed_row.`type_name`;

-- テーブル定義書_被害状況ステータステーブル AK5: 0.不明、1.正常、2.軽度、3.重度
INSERT INTO `damage_status` (`status_code`, `status_name`)
VALUES (0, '不明'), (1, '正常'), (2, '軽度'), (3, '重度') AS seed_row
ON DUPLICATE KEY UPDATE `status_name` = seed_row.`status_name`;

-- テーブル定義書_地震関連性テーブル AK5: 0.不明、1.なし、2.あり
INSERT INTO `earthquake_relation` (`relation_code`, `relation`)
VALUES (0, '不明'), (1, 'なし'), (2, 'あり') AS seed_row
ON DUPLICATE KEY UPDATE `relation` = seed_row.`relation`;

-- テーブル定義書_被害箇所毎被害程度テーブル AK5: 0.判定不能、1.なし、2.軽度、3.中度、4.重度
INSERT INTO `location_severity` (`severity_code`, `severity`)
VALUES (0, '判定不能'), (1, 'なし'), (2, '軽度'), (3, '中度'), (4, '重度') AS seed_row
ON DUPLICATE KEY UPDATE `severity` = seed_row.`severity`;

COMMIT;

-- 実行結果確認（設計書にない既存行も表示する）
SELECT `role_code`, `role_name` FROM `role` ORDER BY `role_code`;
SELECT `provider_code`, `provider_name` FROM `provider` ORDER BY `provider_code`;
SELECT `type_code`, `type_name` FROM `building_type` ORDER BY `type_code`;
SELECT `status_code`, `status_name` FROM `damage_status` ORDER BY `status_code`;
SELECT `relation_code`, `relation` FROM `earthquake_relation` ORDER BY `relation_code`;
SELECT `severity_code`, `severity` FROM `location_severity` ORDER BY `severity_code`;
