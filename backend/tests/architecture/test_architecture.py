from pathlib import Path

from archunitpython import assert_passes, project_files, project_layers

SRC_PATH = str(Path(__file__).resolve().parents[2] / "src" / "app")


def test_dependency_direction_and_layering() -> None:
    """Hexagonal architecture dependency direction.

    entrypoints -> adapters -> application -> domain.
    """
    arch = (
        project_layers(SRC_PATH)
        .layer("domain")
        .defined_by_folder("*domain*")
        .layer("ports")
        .defined_by_folder("*ports*")
        .layer("application")
        .defined_by_folder("*application*")
        .layer("adapters")
        .defined_by_folder("*adapters*")
        .layer("shared_kernel")
        .defined_by_folder("*shared_kernel*")
        .layer("platform")
        .defined_by_folder("*platform*")
        .layer("entrypoints")
        .defined_by_folder("*entrypoints/api")
        .layer("entrypoints")
        .defined_by_folder("*entrypoints/cli")
        .layer("entrypoints")
        .defined_by_folder("*entrypoints/api/system*")
        .layer("api_shared")
        .defined_by_folder("*entrypoints/api/shared*")
        .where_layer("domain")
        .may_only_depend_on_layers("domain", "shared_kernel")
        .where_layer("ports")
        .may_only_depend_on_layers("ports", "domain", "shared_kernel")
        .where_layer("application")
        .may_only_depend_on_layers("application", "ports", "domain", "shared_kernel")
        .where_layer("adapters")
        .may_only_depend_on_layers(
            "adapters",
            "application",
            "ports",
            "domain",
            "shared_kernel",
            "platform",
            "api_shared",
        )
        .where_layer("shared_kernel")
        .may_only_depend_on_layers("shared_kernel")
        .where_layer("platform")
        .may_only_depend_on_layers("platform")
    )
    assert_passes(arch)


def test_domain_layer_has_no_framework_dependencies() -> None:
    """Domain layer must not depend on frameworks (FastAPI, SQLAlchemy, Pydantic)."""
    rule = (
        project_files(SRC_PATH)
        .in_folder("*domain*")
        .should_not()
        .depend_on_external_modules()
        .matching("fastapi*")
        .matching("sqlalchemy*")
        .matching("pydantic*")
    )
    assert_passes(rule)


def test_shared_kernel_has_no_framework_dependencies() -> None:
    """Shared kernel must not depend on frameworks (FastAPI, SQLAlchemy, Pydantic)."""
    rule = (
        project_files(SRC_PATH)
        .in_folder("*shared_kernel*")
        .should_not()
        .depend_on_external_modules()
        .matching("fastapi*")
        .matching("sqlalchemy*")
        .matching("pydantic*")
    )
    assert_passes(rule)


def test_ports_layer_has_no_framework_dependencies() -> None:
    """Ports layer must not depend on frameworks (FastAPI, SQLAlchemy)."""
    rule = (
        project_files(SRC_PATH)
        .in_folder("*ports*")
        .should_not()
        .depend_on_external_modules()
        .matching("fastapi*")
        .matching("sqlalchemy*")
    )
    assert_passes(rule)


def test_application_layer_has_no_framework_dependencies() -> None:
    """Application layer must not depend on frameworks (FastAPI, SQLAlchemy)."""
    rule = (
        project_files(SRC_PATH)
        .in_folder("*application*")
        .should_not()
        .depend_on_external_modules()
        .matching("fastapi*")
        .matching("sqlalchemy*")
    )
    assert_passes(rule)


def test_no_circular_dependencies() -> None:
    """The application must have no circular dependencies across files."""
    rule = project_files(SRC_PATH).should().have_no_cycles()
    assert_passes(rule)
