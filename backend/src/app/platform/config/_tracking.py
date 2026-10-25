"""Record the highest-priority source supplying each settings field."""

from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from typing import TYPE_CHECKING, Any, cast

from pydantic import AliasChoices, AliasPath, PrivateAttr
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SecretsSettingsSource,
)

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo


_collector: ContextVar[dict[str, tuple[int, str]] | None] = ContextVar(
    "settings_sources", default=None
)
# Pydantic sources and construction accept arbitrary validated input values.
type Source = Callable[[], dict[str, Any]]


def _label(source: Source) -> str:
    for source_type, label in (
        (InitSettingsSource, "init"),
        (DotEnvSettingsSource, "dotenv"),
        (EnvSettingsSource, "env"),
        (SecretsSettingsSource, "secret_file"),
    ):
        if isinstance(source, source_type):
            return label
    return str(getattr(source, "source_label", type(source).__name__))


class _Recorder(PydanticBaseSettingsSource):
    def __init__(self, settings_cls: type[BaseSettings], source: Source) -> None:
        super().__init__(settings_cls)
        self.source = source
        self.__name__ = getattr(source, "__name__", type(source).__name__)

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        raise NotImplementedError

    def __call__(self) -> dict[str, Any]:
        if isinstance(self.source, PydanticBaseSettingsSource):
            self.source._set_current_state(self.current_state)
            self.source._set_settings_sources_data(self.settings_sources_data)
        values = self.source()
        collector = _collector.get()
        if collector is not None:
            for name, field in self.settings_cls.model_fields.items():
                alias = field.validation_alias
                aliases = alias.choices if isinstance(alias, AliasChoices) else [alias]
                paths = [
                    a.path if isinstance(a, AliasPath) else [a]
                    for a in aliases
                    if a is not None
                ]
                paths.append([name])
                for rank, path in enumerate(paths):
                    value: Any = values
                    try:
                        for key in path:
                            value = value[key]
                    except KeyError, IndexError, TypeError:
                        continue
                    # AliasChoices chooses its preferred key after sources merge.
                    previous = collector.get(name)
                    if previous is None or rank < previous[0]:
                        collector[name] = (rank, _label(self.source))
                    break
        return values


def tracked_sources[**P](
    method: Callable[P, tuple[PydanticBaseSettingsSource, ...]],
) -> Callable[P, tuple[PydanticBaseSettingsSource, ...]]:
    """Track the sources returned by a base or subclass customisation hook."""

    @wraps(method)
    def wrapped(
        *args: P.args, **kwargs: P.kwargs
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources = method(*args, **kwargs)
        settings_cls = cast("type[BaseSettings]", args[0])
        return tuple(
            s if isinstance(s, _Recorder) else _Recorder(settings_cls, s)
            for s in sources
        )

    return wrapped


class TrackedSettings(BaseSettings):
    """Settings with construction-local provenance, excluded from serialisation."""

    _sources: dict[str, str] = PrivateAttr(default_factory=dict)

    def __init_subclass__(cls, **kwargs: Any) -> None:  # noqa: ANN401 - Pydantic class options
        super().__init_subclass__(**kwargs)
        override = cls.__dict__.get("settings_customise_sources")
        if override is not None:
            type.__setattr__(
                cls,
                "settings_customise_sources",
                classmethod(tracked_sources(override.__func__)),
            )

    def __init__(self, **values: Any) -> None:  # noqa: ANN401 - Pydantic input contract
        sources: dict[str, tuple[int, str]] = {}
        token = _collector.set(sources)
        try:
            super().__init__(**values)
            self._sources = {name: label for name, (_, label) in sources.items()}
        finally:
            _collector.reset(token)

    @classmethod
    @tracked_sources
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return super().settings_customise_sources(
            settings_cls,
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    def source_of(self, field: str) -> str:
        """Return the winning source label for a field name."""
        if field not in type(self).model_fields:
            raise KeyError(field)
        return self._sources.get(field, "default")

    def is_pinned(self, field: str) -> bool:
        """Return whether deployment configuration supplied the field."""
        return self.source_of(field) in {"env", "dotenv", "secret_file"}

    def sources(self) -> dict[str, str]:
        """Return a copy of the source map, including defaults."""
        return {name: self.source_of(name) for name in type(self).model_fields}
