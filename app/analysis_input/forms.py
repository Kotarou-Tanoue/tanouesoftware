# app/analysis_input/forms.py
from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import InputRequired, DataRequired, NumberRange

# 「登録済みの建物」セレクトの先頭(新規入力を意味する)
NEW_BUILDING_VALUE = 0
NEW_BUILDING_LABEL = "新しい建物を入力する"

# 建物の種類。建物登録の担当者とそろえること(仮)
BUILDING_TYPE_CHOICES = [
    ("", "選択してください"),
    ("1", "戸建て"),
    ("2", "集合住宅")
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
        buildings: Buildingモデルのリスト(id, name属性が必要)"""
        self.building.choices = [(NEW_BUILDING_VALUE, NEW_BUILDING_LABEL)] + [
            (b.id, b.name) for b in buildings
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
        validators=[DataRequired(message="建物名を入力してください")],
        render_kw={"placeholder": "例:自宅"},
    )
    building_type = SelectField(
        "建物の種類",
        choices=BUILDING_TYPE_CHOICES,
        validators=[DataRequired(message="建物の種類を選択してください")],
    )
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
        validators=[DataRequired(message="市区町村を入力してください")],
        render_kw={"placeholder": "例:熊本市西区"},
    )
    submit_new = SubmitField("次へ(被害状況入力)")

    def to_dict(self):
        """セッション保存/DB保存用のdict"""
        return {
            "name": self.name.data.strip(),
            "building_type": self.building_type.data,
            "age_years": self.age_years.data,
            "prefecture": self.prefecture.data,
            "city": self.city.data.strip(),
        }
