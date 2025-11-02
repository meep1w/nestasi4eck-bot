from sqlalchemy.orm import DeclarativeBase, declared_attr
from sqlalchemy import MetaData


# Единый metadata с нейминговыми конвенциями — аккуратные имена ключей/индексов
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    metadata = metadata

    # Имена таблиц по умолчанию — из имени класса в snake_case можно не городить,
    # у нас явные __tablename__ в моделях; но оставим хук на будущее.
    @declared_attr.directive
    def __tablename__(cls) -> str:  # type: ignore[override]
        # Если в модели задан __tablename__, SQLAlchemy его использует.
        # Этот метод сработает, если забыли указать имя таблицы.
        return cls.__name__.lower()
