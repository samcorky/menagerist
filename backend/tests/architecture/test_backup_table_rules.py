import importlib
from pathlib import Path

import app.modules
from app.modules.backup.adapters.persistence.table_rules import TABLE_RULES
from app.platform.database import Base


def test_every_model_table_has_an_explicit_backup_rule() -> None:
    """New schema tables must choose their backup policy explicitly."""
    for root in app.modules.__path__:
        for model in Path(root).glob("*/adapters/persistence/models.py"):
            name = model.relative_to(root).with_suffix("").parts
            importlib.import_module("app.modules." + ".".join(name))
    assert set(Base.metadata.tables) == TABLE_RULES.keys() - {"alembic_version"}
