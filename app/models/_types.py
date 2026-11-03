import enum

from sqlalchemy import Enum


def enum_column(enum_cls: type[enum.Enum]) -> Enum:
    """Store enum *values* as VARCHAR + CHECK. Portable and migration-friendly."""
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda cls: [member.value for member in cls],
        name=enum_cls.__name__.lower(),
    )
