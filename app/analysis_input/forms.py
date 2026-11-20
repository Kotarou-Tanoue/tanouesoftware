# app/analysis_input/forms.py
from datetime import datetime

from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange

# ======================================================================
# ステップ1: 建物情報入力
# ======================================================================

# 「登録済みの建物」セレクトの先頭(新規入力を意味する)
NEW_BUILDING_VALUE = 0
NEW_BUILDING_LABEL = "新しい建物を入力する"

# 建物の種類。値は building_type テーブルの type_code と一致させること
BUILDING_TYPE_CHOICES = [
    ("", "選択してください"),
    ("1", "戸建て"),
    ("2", "集合住宅"),
]

PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]
PREFECTURE_CHOICES = [("", "選択してください")] + [(p, p) for p in PREFECTURES]


def _current_year():
    return datetime.now().year


def building_label(b):
    """セレクトに表示する建物名。例: 自宅（戸建て住宅・築15年）
    b: Buildingモデル。b.building_type は BuildingType(関連テーブル)"""
    age = max(0, _current_year() - b.built_year)
    return f"{b.building_name}（{b.building_type.type_name}・築{age}年）"


class ExistingBuildingForm(FlaskForm):
    """登録済みの建物から選択(ログイン時のみ使う)"""

    building = SelectField(
        "登録済みの建物",
        coerce=int,
        choices=[(NEW_BUILDING_VALUE, NEW_BUILDING_LABEL)],
        default=NEW_BUILDING_VALUE,
    )
    submit_existing = SubmitField("この建物で進む")

    def set_choices(self, buildings):
        """ログイン中のユーザーの建物一覧をセットする。
        buildings: Buildingモデルのリスト"""
        self.building.choices = [(NEW_BUILDING_VALUE, NEW_BUILDING_LABEL)] + [
            (b.building_id, building_label(b)) for b in buildings
        ]

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators=extra_validators)
        if ok and self.building.data == NEW_BUILDING_VALUE:
            self.building.errors = list(self.building.errors) + [
                "登録済みの建物を選択してください(新しい建物は下のフォームに入力してください)"
            ]
            return False
        return ok


class BuildingForm(FlaskForm):
    """新しい建物の入力"""

    name = StringField(
        "建物名",
        validators=[
            DataRequired(message="建物名を入力してください"),
            Length(max=100, message="100文字以内で入力してください"),  # building_name: String(100)
        ],
        render_kw={"placeholder": "例:自宅"},
    )
    building_type = SelectField(
        "建物の種類",
        choices=BUILDING_TYPE_CHOICES,
        validators=[DataRequired(message="建物の種類を選択してください")],
    )
    # 画面では「築年数」で入力してもらい、to_dict() で建築年に変換する
    # 0年(新築)も有効なので DataRequired ではなく InputRequired を使う
    age_years = IntegerField(
        "築年数",
        validators=[
            InputRequired(message="築年数を入力してください"),
            NumberRange(min=0, max=150, message="0〜150の整数で入力してください"),
        ],
        render_kw={"placeholder": "例:15", "min": 0, "max": 150},
    )
    prefecture = SelectField(
        "都道府県",
        choices=PREFECTURE_CHOICES,
        validators=[DataRequired(message="都道府県を選択してください")],
    )
    city = StringField(
        "市区町村",
        validators=[
            DataRequired(message="市区町村を入力してください"),
            Length(max=100, message="100文字以内で入力してください"),  # city: String(100)
        ],
        render_kw={"placeholder": "例:熊本市西区"},
    )
    submit_new = SubmitField("次へ(被害状況入力)")

    def to_dict(self):
        """セッション保存/DB保存用のdict。キー名はBuildingモデルのカラム名に合わせてある。
        Building(user_id=..., **form.to_dict()) でそのまま保存できる"""
        return {
            "building_name": self.name.data.strip(),
            "building_type_code": int(self.building_type.data),   # 選択値は文字列なのでintに変換
            "built_year": _current_year() - self.age_years.data,  # 築年数 → 建築年
            "prefecture": self.prefecture.data,
            "city": self.city.data.strip(),
        }


# ======================================================================
# ステップ2: 被害状況入力
# ======================================================================

# 「その他」を選んだときは、下の自由入力欄に書いた文字がDBに保存される
OTHER_VALUE = "その他(自由入力可)"

# 画面の選択肢(モックのとおり)。値はそのまま damage_location の文字列カラムに保存される。
LOCATION_NAMES = [
    "和室", "洋室", "キッチン", "浴室", "トイレ", "廊下", "階段",
    "ベランダ", "外壁", "屋根", "庭", "車庫・ガレージ", OTHER_VALUE,
]
LOCATION_TYPES = ["壁", "床", "天井", OTHER_VALUE]
DAMAGE_TYPES = ["ひび割れ", "剥がれ", "変形", "破損", "傾き", "沈下", "倒壊", OTHER_VALUE]

# マスタテーブルのカラム名(選択肢をDBから作るために使う)
STATUS_CODE_ATTR, STATUS_NAME_ATTR = "status_code", "status_name"        # DamageStatus
RELATION_CODE_ATTR, RELATION_NAME_ATTR = "relation_code", "relation"    # EarthquakeRelation

# ★ 画面に出す選択肢 [(コード, 画面の文言), ...] を、表示したい順に書く。
#    コードは damage_status / earthquake_relation テーブルの値に必ず合わせること。
#    空のままにすると、DBの行(名前は5文字以内)がそのまま選択肢になる。
#    マスタの中身:  damage_status       = 0:不明 / 1:正常 / 2:軽度 / 3:重度
#                   earthquake_relation = 0:不明 / 1:なし / 2:あり
STATUS_CHOICES = {
    "door_window_status": [
        (0, "わからない・確認していない"),
        (1, "正常に開閉できる"),  # 1: 正常
        (2, "開閉しにくい"),      # 2: 軽度
        (3, "開閉できない"),      # 3: 重度
    ],
    "noise_status": [
        (0, "わからない・確認していない"),
        (1, "いいえ、特にない"),  # 1: 正常
        (2, "かすかに聞こえる"),  # 2: 軽度
        (3, "聞こえる"),          # 3: 重度
    ],
    "tilt_status": [
        (0, "わからない・確認していない"),
        (1, "いいえ、特に感じない"),  # 1: 正常
        (2, "少し感じる"),            # 2: 軽度
        (3, "感じる"),                # 3: 重度
    ],
}
RELATION_CHOICES = [
    (0, "わからない"),
    (1, "地震の前からあった"),  # 1: なし(地震とは関連なし)
    (2, "地震の後に発生した"),  # 2: あり(地震と関連あり)
]

# 建物全体の状態(DamageReport のカラム名と同じ)
STATUS_FIELDS = ("door_window_status", "noise_status", "tilt_status")

# 「わからない」にあたる選択肢を、初期値にするための目印(文言に含まれる語)
UNKNOWN_KEYWORDS = ("わからない", "不明")


def _build_choices(rows, code_attr, name_attr, mapping):
    """セレクトの選択肢を作る。戻り値: (選択肢のリスト, 「わからない」のコード or None)

    mapping があればそれを使い(画面の文言・順番を固定)、なければDBの行から作る。
    「わからない」の選択肢がなければ、「選択してください」を先頭に足す。"""
    db_codes = {str(getattr(r, code_attr)) for r in rows}
    if mapping:
        pairs = [(str(code), label) for code, label in mapping]
        missing = [code for code, _ in pairs if code not in db_codes]
        if missing:
            raise ValueError(f"マスタテーブルにないコードが選択肢に指定されています: {missing}")
    else:
        pairs = [(str(getattr(r, code_attr)), getattr(r, name_attr)) for r in rows]

    default = next(
        (code for code, label in pairs if any(word in (label or "") for word in UNKNOWN_KEYWORDS)),
        None,
    )
    if default is None:
        pairs.insert(0, ("", "選択してください"))
    return pairs, default


def _simple_choices(values):
    return [(v, v) for v in values]


class DamageEntryForm(FlaskForm):
    """被害情報1件分の入力(写真は views.py 側で request.files から受け取る)

    部屋・被害箇所・被害の種類は、「その他」を選ぶと自由入力欄(〜_other)が使われる。"""

    location_name = SelectField(
        "被害を受けた部屋・場所",
        choices=_simple_choices(LOCATION_NAMES),
        validators=[DataRequired(message="被害を受けた部屋・場所を選択してください")],
    )
    location_name_other = StringField(
        "被害を受けた場所(自由入力)",
        render_kw={"placeholder": "被害を受けた場所を入力してください"},
    )
    location_type = SelectField(
        "被害箇所",
        choices=_simple_choices(LOCATION_TYPES),
        validators=[DataRequired(message="被害箇所を選択してください")],
    )
    location_type_other = StringField(
        "被害箇所(自由入力)",
        render_kw={"placeholder": "被害箇所を入力してください"},
    )
    damage_type = SelectField(
        "被害の種類",
        choices=_simple_choices(DAMAGE_TYPES),
        validators=[DataRequired(message="被害の種類を選択してください")],
    )
    damage_type_other = StringField(
        "被害の種類(自由入力)",
        render_kw={"placeholder": "被害の種類を入力してください"},
    )
    earthquake_relation = SelectField(
        "この被害は地震の後に発生したものですか？",
        validators=[DataRequired(message="選択してください")],
    )
    submit_add = SubmitField("＋ この被害情報を追加")

    # (選択肢のフィールド, 自由入力のフィールド, DBの最大文字数, エラー文に使う名前)
    _OTHER_RULES = (
        ("location_name", "location_name_other", 50, "被害を受けた場所"),   # location_name: String(50)
        ("location_type", "location_type_other", 30, "被害箇所"),           # location_type: String(30)
        ("damage_type", "damage_type_other", 30, "被害の種類"),             # damage_type: String(30)
    )

    def set_relation_choices(self, rows):
        """earthquake_relation テーブルの行から選択肢を作る(POSTのときも必須)。
        戻り値: 「わからない」のコード(なければNone)"""
        pairs, default = _build_choices(rows, RELATION_CODE_ATTR, RELATION_NAME_ATTR, RELATION_CHOICES)
        self.earthquake_relation.choices = pairs
        return default

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators=extra_validators)
        # 「その他」を選んだ項目だけ、自由入力を必須にする(選んでいない項目の自由入力は無視)
        for select_name, other_name, max_length, label in self._OTHER_RULES:
            if getattr(self, select_name).data != OTHER_VALUE:
                continue
            other = getattr(self, other_name)
            text = (other.data or "").strip()
            if not text:
                other.errors = list(other.errors) + [f"{label}を入力してください"]
                ok = False
            elif len(text) > max_length:
                other.errors = list(other.errors) + [f"{max_length}文字以内で入力してください"]
                ok = False
        return ok

    def _value(self, select_name, other_name):
        """保存する値。「その他」のときは自由入力の文字、それ以外は選んだ選択肢。"""
        value = getattr(self, select_name).data
        if value == OTHER_VALUE:
            return (getattr(self, other_name).data or "").strip()
        return value

    def to_dict(self, photo_keys):
        """セッション保存用のdict(DamageLocation のカラム名に合わせてある)"""
        return {
            "location_name": self._value("location_name", "location_name_other"),
            "location_type": self._value("location_type", "location_type_other"),
            "damage_type": self._value("damage_type", "damage_type_other"),
            "earthquake_relation": int(self.earthquake_relation.data),
            "photo_keys": list(photo_keys),  # 写真のS3オブジェクトキー
        }


class BuildingStatusForm(FlaskForm):
    """建物全体の状態についての質問(3問)"""

    door_window_status = SelectField(
        "ドアや窓は正常に開閉できますか？",
        validators=[DataRequired(message="選択してください")],
    )
    noise_status = SelectField(
        "建物から普段と違う音がしますか？",
        validators=[DataRequired(message="選択してください")],
    )
    tilt_status = SelectField(
        "建物の傾きや床の傾斜を感じますか？",
        validators=[DataRequired(message="選択してください")],
    )
    submit_analyze = SubmitField("AI分析を開始する")

    def set_choices(self, rows):
        """damage_status テーブルの行から、質問ごとの選択肢を作る(POSTのときも必須)。
        戻り値: {質問のフィールド名: 「わからない」のコード or None}"""
        defaults = {}
        for name in STATUS_FIELDS:
            pairs, default = _build_choices(
                rows, STATUS_CODE_ATTR, STATUS_NAME_ATTR, STATUS_CHOICES.get(name)
            )
            getattr(self, name).choices = pairs
            defaults[name] = default
        return defaults