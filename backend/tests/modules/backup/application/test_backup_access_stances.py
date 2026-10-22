from app.modules.backup.application.create_backup import CreateBackup
from app.modules.backup.application.delete_backup import DeleteBackup
from app.modules.backup.application.export_user_data import ExportUserData
from app.modules.backup.application.import_user_archive import ImportUserArchive
from app.modules.backup.application.import_user_data import ImportUserData
from app.modules.backup.application.list_backups import ListBackups
from app.modules.backup.application.open_backup import OpenBackup
from app.modules.backup.application.open_user_export import OpenUserExport
from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.application.prune_backups import PruneBackups
from app.modules.backup.application.restore_backup import RestoreBackup
from app.modules.backup.application.restore_on_first_run import RestoreOnFirstRun
from app.modules.backup.application.upload_backup import UploadBackup
from app.modules.backup.application.verify_backup import VerifyBackup
from app.shared_kernel.access import Content, Public, Requires


def test_first_run_restore_is_public() -> None:
    """It runs with the anonymous actor behind the setup gate."""
    assert RestoreOnFirstRun.access == Public()


def test_personal_archives_are_content() -> None:
    """Each caller exports and imports only their own content."""
    for use_case in (ExportUserData, ImportUserData, ImportUserArchive, OpenUserExport):
        assert use_case.access == Content()


def test_instance_archives_keep_their_permissions() -> None:
    """Instance archive use cases are unchanged: the same permission each."""
    assert {
        CreateBackup: CreateBackup.access,
        UploadBackup: UploadBackup.access,
        ListBackups: ListBackups.access,
        OpenBackup: OpenBackup.access,
        VerifyBackup: VerifyBackup.access,
        DeleteBackup: DeleteBackup.access,
        PruneBackups: PruneBackups.access,
        RestoreBackup: RestoreBackup.access,
    } == {
        CreateBackup: Requires(BackupPermission.CREATE),
        UploadBackup: Requires(BackupPermission.CREATE),
        ListBackups: Requires(BackupPermission.READ),
        OpenBackup: Requires(BackupPermission.READ),
        VerifyBackup: Requires(BackupPermission.READ),
        DeleteBackup: Requires(BackupPermission.DELETE),
        PruneBackups: Requires(BackupPermission.DELETE),
        RestoreBackup: Requires(BackupPermission.RESTORE),
    }
