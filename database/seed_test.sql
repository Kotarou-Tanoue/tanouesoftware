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
-- あくまでテストデータであるため、本番環境(AWS RDS)では実行しないこと。

SET NAMES utf8mb4;
START TRANSACTION;

-- テーブル定義書_利用者テーブル
INSERT INTO `user` (`user_id`, `role_code`)
VALUES (1, 0), (2, 1), (3, 1) AS seed_row
ON DUPLICATE KEY UPDATE `role_code` = seed_row.`role_code`;

-- テーブル定義書_利用者認証テーブル
INSERT INTO `user_auth` (`provider_code`, `provider_user_id`, `user_id`, `password_hash`)
VALUES (0, 'admin@example.com', 1, 'scrypt:32768:8:1$851ogxqNjvmSeXok$ac4912bc9587a73443df585a98896865b2df4a61fbc6dbf7792bce63faa7fd47de4d3996b8f478455767a5bb8bb323ef9c8164f89f2e81e9e7a8f0874620138f') AS seed_row
ON DUPLICATE KEY UPDATE `password_hash` = seed_row.`password_hash`;

-- テーブル定義書_建物テーブル
INSERT INTO `building` (`building_id`, `user_id`, `building_name`, `prefecture`, `city`, `built_year`, `building_type_code`)
VALUES (1, 2, '自宅', '熊本県', '熊本市西区', 2000, 2), (2, 2, '実家', '熊本県', '八代市', 1970, 1), (3, 2, '別荘', '長野県', '北佐久郡軽井沢町', 2020, 1) AS seed_row
ON DUPLICATE KEY UPDATE `building_name` = seed_row.`building_name`;

-- テーブル定義書_被害状況テーブル
INSERT INTO `damage_report` (`report_id`, `building_id`, `door_window_status`, `noise_status`, `tilt_status`)
VALUES (1, 1, 2, 2, 2), (2, 2, 3, 3, 3) AS seed_row
ON DUPLICATE KEY UPDATE `building_id` = seed_row.`building_id`;

-- テーブル定義書_被害箇所テーブル
INSERT INTO `damage_location` (`location_id`, `report_id`, `location_name`, `location_type`, `damage_type`, `earthquake_relation`)
VALUES (1, 1, '洋室', '壁', 'ひび割れ', 2), (2, 1, '浴室', '壁', 'ひび割れ', 2), (3, 2, '玄関', '床', 'ひび割れ', 2) AS seed_row
ON DUPLICATE KEY UPDATE `location_name` = seed_row.`location_name`;

-- テーブル定義書_被害写真テーブル
INSERT INTO `damage_photo` (`photo_id`, `location_id`, `s3_object_key`)
VALUES (1, 1, 'test_images/sample01.png'), (2, 2, 'test_images/sample02.png'), (3, 3, 'test_images/sample01.png') AS seed_row
ON DUPLICATE KEY UPDATE `s3_object_key` = seed_row.`s3_object_key`;

-- テーブル定義書_分析履歴テーブル
INSERT INTO `analysis_history` (`analysis_id`, `report_id`, `damage_level`, `repair_cost_min`, `repair_cost_max`, `description`)
VALUES (1, 1, 3, 50000, 2000000, '洋室の壁に20cmほどのひび割れ、浴室の壁に30cmほどのひび割れ・壁紙のしわ寄せ'), (2, 2, 5, 200000, 500000, '玄関のタイルが広範囲にわたってひび割れ・ずれ') AS seed_row
ON DUPLICATE KEY UPDATE `damage_level` = seed_row.`damage_level`;

-- テーブル定義書_チャット履歴テーブル
INSERT INTO `chat_history` (`chat_id`, `analysis_id`, `user_question`, `ai_answer`)
VALUES (1, 1, 'この被害はすぐに修理すべきですか？', '建物の倒壊等の大きな被害につながる可能性は低いと推測されるため、修理の緊急性はないと考えられます。'), (2, 1, '修理をする必要はないですか？', '分析結果はあくまで推測ですので、修理が必要かどうかについては自治体や修理業者に相談することをおすすめします。') AS seed_row
ON DUPLICATE KEY UPDATE `ai_answer` = seed_row.`ai_answer`;


-- 確認用SQL
-- 利用者
SELECT * FROM `user`
WHERE `user_id` IN (1, 2, 3);

-- 利用者認証
SELECT
    `provider_code`,
    `provider_user_id`,
    `user_id`,
    CASE
        WHEN `password_hash` IS NOT NULL THEN '登録済み'
        ELSE '未登録'
    END AS password_status
FROM `user_auth`
WHERE `user_id` IN (1, 2, 3);

-- 建物
SELECT * FROM `building`
WHERE `building_id` IN (1, 2, 3);

-- 被害報告
SELECT * FROM `damage_report`
WHERE `report_id` IN (1, 2);

-- 被害箇所
SELECT * FROM `damage_location`
WHERE `location_id` IN (1, 2, 3);

-- 被害写真
SELECT * FROM `damage_photo`
WHERE `photo_id` IN (1, 2, 3);

-- 分析履歴
SELECT * FROM `analysis_history`
WHERE `analysis_id` IN (1, 2);

-- チャット履歴
SELECT * FROM `chat_history`
WHERE `chat_id` IN (1, 2);