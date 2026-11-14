from typing import TYPE_CHECKING, Any

from app.modules.presets.application.create_preset import CreatePreset
from app.modules.presets.application.delete_preset import DeletePreset
from app.modules.presets.application.export_presets import ExportPresets
from app.modules.presets.application.get_preset import GetPreset
from app.modules.presets.application.import_presets import ImportPresets
from app.modules.presets.application.list_presets import ListPresets
from app.modules.presets.application.match_presets import MatchPresets
from app.modules.presets.application.permissions import PresetPermission
from app.modules.presets.application.update_preset import UpdatePreset
from app.shared_kernel.access import Access, Content

if TYPE_CHECKING:
    from app.shared_kernel.cqrs import UseCase

READ = Content(PresetPermission.PRESET_READ)
WRITE = Content(PresetPermission.PRESET_WRITE)

STANCES: dict[type[UseCase[Any, Any]], Access] = {
    ExportPresets: READ,
    GetPreset: READ,
    ListPresets: READ,
    MatchPresets: READ,
    CreatePreset: WRITE,
    DeletePreset: WRITE,
    ImportPresets: WRITE,
    UpdatePreset: WRITE,
}


def test_presets_are_owned_content_gated_by_the_preset_permissions() -> None:
    """Presets are a person's own content, gated by the read and write permissions."""
    assert {use_case: use_case.access for use_case in STANCES} == STANCES
