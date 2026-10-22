from app.modules.presets.application.create_preset import CreatePreset
from app.modules.presets.application.delete_preset import DeletePreset
from app.modules.presets.application.export_presets import ExportPresets
from app.modules.presets.application.get_preset import GetPreset
from app.modules.presets.application.import_presets import ImportPresets
from app.modules.presets.application.list_presets import ListPresets
from app.modules.presets.application.update_preset import UpdatePreset
from app.shared_kernel.access import Shared


def test_presets_are_a_shared_catalogue() -> None:
    """Any signed-in actor, and the example-pack bridge, may use presets."""
    for use_case in (
        CreatePreset,
        DeletePreset,
        ExportPresets,
        GetPreset,
        ImportPresets,
        ListPresets,
        UpdatePreset,
    ):
        assert use_case.access == Shared()
