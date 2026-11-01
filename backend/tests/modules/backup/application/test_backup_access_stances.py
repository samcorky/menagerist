from app.modules.backup.application.create_backup import CreateBackup
from app.modules.backup.application.delete_backup import DeleteBackup
from app.modules.backup.application.delete_user_export import DeleteUserExport
from app.modules.backup.application.export_user_data import ExportUserData
from app.modules.backup.application.import_user_archive import ImportUserArchive
from app.modules.backup.application.import_user_data import ImportUserData
from app.modules.backup.application.list_backups import ListBackups
from app.modules.backup.application.list_user_exports import ListUserExports
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


EXPORT = Content(BackupPermission.EXPORT_OWN_DATA)
IMPORT = Content(BackupPermission.IMPORT_OWN_DATA)


def test_personal_archives_are_content() -> None:
    """Each caller exports and imports only their own content, given the permission."""
    assert {
        ExportUserData: ExportUserData.access,
        OpenUserExport: OpenUserExport.access,
        ListUserExports: ListUserExports.access,
        DeleteUserExport: DeleteUserExport.access,
        ImportUserData: ImportUserData.access,
        ImportUserArchive: ImportUserArchive.access,
    } == {
        ExportUserData: EXPORT,
        OpenUserExport: EXPORT,
        ListUserExports: EXPORT,
        DeleteUserExport: EXPORT,
        ImportUserData: IMPORT,
        ImportUserArchive: IMPORT,
    }


def test_import_archive_needs_what_its_inner_use_case_needs() -> None:
    """The composite runs ImportUserData under the same actor."""
    needed = {ImportUserArchive.access, ImportUserData.access}
    assert needed == {Content(BackupPermission.IMPORT_OWN_DATA)}


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
