"""全Modelを読み込み、SQLAlchemyのメタデータに登録する。"""

from .analysis_history import AnalysisHistory
from .building import Building
from .building_type import BuildingType
from .chat_history import ChatHistory
from .damage_location import DamageLocation
from .damage_photo import DamagePhoto
from .damage_report import DamageReport
from .damage_status import DamageStatus
from .earthquake_relation import EarthquakeRelation
from .location_severity import LocationSeverity
from .provider import Provider
from .role import Role
from .user import User
from .user_auth import UserAuth

__all__ = [
    "AnalysisHistory",
    "Building",
    "BuildingType",
    "ChatHistory",
    "DamageLocation",
    "DamagePhoto",
    "DamageReport",
    "DamageStatus",
    "EarthquakeRelation",
    "LocationSeverity",
    "Provider",
    "Role",
    "User",
    "UserAuth",
]
