from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


class AllowAllAuthorizationAdapter:
    """v1 stub `AuthorizationPort` - every actor may perform every action.

    Lives at the composition root rather than in a module because no
    bounded context owns authorization yet. Once an `identity` module
    exists (the OIDC roadmap step), this gets replaced wholesale by wiring
    that module's real adapter in `dependencies.py` - no route or use case
    needs to change, since they only ever depended on `AuthorizationPort`.
    """

    async def check(self, actor: Actor, action: str) -> None:
        """Always permit - v1 is single-owner with no enforcement yet."""
