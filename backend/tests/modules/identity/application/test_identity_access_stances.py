from app.modules.identity.application.change_password import ChangePassword
from app.modules.identity.application.get_current_user import GetCurrentUser
from app.modules.identity.application.get_setup_status import GetSetupStatus
from app.modules.identity.application.has_administrator import HasAdministrator
from app.modules.identity.application.list_own_sessions import ListOwnSessions
from app.modules.identity.application.revoke_other_sessions import RevokeOtherSessions
from app.modules.identity.application.revoke_own_session import RevokeOwnSession
from app.modules.identity.application.set_own_display_name import SetOwnDisplayName
from app.modules.identity.application.setup_first_admin import SetupFirstAdmin
from app.modules.identity.application.sign_in import SignIn
from app.modules.identity.application.sign_out import SignOut
from app.shared_kernel.access import OwnAccount, Public


def test_sign_in_and_setup_flows_are_public() -> None:
    """Callers are anonymous, or the system actor at startup."""
    for use_case in (
        SignIn,
        SignOut,
        SetupFirstAdmin,
        GetCurrentUser,
        GetSetupStatus,
        HasAdministrator,
    ):
        assert use_case.access == Public()


def test_own_account_actions_need_a_signed_in_session() -> None:
    """Changing your own password or sessions is for the signed-in user only."""
    for use_case in (
        ChangePassword,
        RevokeOtherSessions,
        RevokeOwnSession,
        SetOwnDisplayName,
        ListOwnSessions,
    ):
        assert use_case.access == OwnAccount()
