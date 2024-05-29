from inspect import Parameter, Signature, signature
from typing import Any, Generic, Literal, Optional, Self, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from pydantic import BaseModel
from sqlmodel import Session, SQLModel, col, func, or_, select
from sqlmodel.sql.expression import SelectOfScalar

from app.db import get_session
from app.security import get_current_active_user


class BaseRead(BaseModel):
    @classmethod
    def from_db(cls: type[Self], obj: SQLModel) -> Self:
        return cls(**obj.model_dump())


T = TypeVar("T", bound=BaseRead)


class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    data: list[T]


class BaseCreate(BaseModel):
    pass


class BaseUpdate(BaseModel):
    pass


class BaseDB(SQLModel):
    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.__read_class__: type[BaseRead] = getattr(cls, "__read_class__", BaseRead)
        if getattr(cls, "create_class", None) and getattr(cls, "update_class", None):
            cls.__create_class__: type[BaseCreate] = cls.__create_class__
            cls.__update_class__: type[BaseUpdate] = cls.__update_class__
        cls.__default_filters__: list[str] = []

    @classmethod
    def to_db(cls: type[Self], raw_obj: dict[str, Any]):
        return cls(**raw_obj)

    @classmethod
    def _class_vars(cls: type[Self]) -> list[str]:
        return [
            field
            for field in dir(cls)
            if not field.startswith("_")
            and not callable(getattr(cls, field))
            and not field.startswith("model")
            and field != "metadata"
        ]

    @classmethod
    def _get_default_filters(cls: type[Self]) -> list[str]:
        if cls.__default_filters__:
            return cls.__default_filters__

        defaults = []
        for cls_attr in cls._class_vars():
            for clazz in cls.__mro__:
                annotations = getattr(clazz, "__annotations__", [])
                cls_annotation = annotations.get(cls_attr, None)
                if not cls_annotation:
                    continue
                if cls_annotation in [str, Optional[str]]:
                    defaults.append[cls_attr]

        cls.__default_filters__ = defaults
        return cls.__default_filters__

    @classmethod
    def _as_id_endpoint(cls: type[Self]):
        return "/{" + "}/{".join([key.name for key in cls.__table__.primary_key]) + "}"

    @classmethod
    def _create_id_signature(cls: type[Self], old_sig: Signature):
        """
        Generates a new function signature, with the primary keys of this class being appended before the kwargs.
        kwargs must be provided in the original function
        """
        TYPE_MAP = {"VARCHAR": str, "INTEGER": int}
        modified_sig = old_sig.parameters.copy()
        modified_sig.pop("kwargs")
        primary_keys = cls.__table__.primary_key
        sig_type_map = {}
        for key in primary_keys:
            column = cls.__table__.c.get(key.name)
            try:
                c_type = column.type.python_type
            except NotImplementedError:
                c_type = TYPE_MAP.get(str(column.type))
            sig_type_map[key.name] = c_type
        for key in primary_keys:
            sig_type = sig_type_map[key.name]
            modified_sig[key.name] = Parameter(
                key.name, Parameter.KEYWORD_ONLY, annotation=sig_type
            )
        return Signature(list[modified_sig.values()])

    def _as_id_tuple(self: Self) -> tuple:
        primary_keys = self.__class__.__table__.primary_key
        id_data = []
        for key in primary_keys:
            id_data.append(getattr(self, key.name))
        return tuple(id_data)

    def validate(self: Self) -> tuple[bool, str]:
        """
        Validates an object, or returns an error message indicating the validation failure
        """
        return True, ""

    @classmethod
    def apply_filter(cls: type[Self], query: SelectOfScalar, filter: str) -> SelectOfScalar:
        or_args = [
            func.lower(col(getattr(cls, or_arg))).contains(filter)
            for or_arg in cls._get_default_filters()
        ]
        return query.where(or_(*or_args))

    @classmethod
    def register_read_single(cls, *, router: APIRouter, route: str, scopes: list[str]):
        router.add_api_route(
            f"/{route}" + cls._as_id_endpoint(),
            cls._read_single_object_wrapper(scopes, cls.__read_class__),
            methods=["GET"],
            response_model=cls.__read_class__,
            name=f"Read {cls.__name__.replace("DB", "")} by ID",
            description=f"Retrieves a single object of type {cls.__name__}, filtering by ID",
        )

    @classmethod
    def register_read_list(cls, *, router: APIRouter, route: str, scopes: list[str]):
        router.add_api_route(
            f"/{route}",
            cls._read_list_object_wrapper(scopes, cls.__read_class__),
            methods=["GET"],
            response_model=PaginatedResponse[cls.__read_class__],
            name=f"Read list of {cls.__name__.replace("DB", "")}",
            description=f"Reads a paginated list of {cls.__name__}",
        )

    @classmethod
    def register_create(cls, *, router: APIRouter, route: str, scopes: list[str]):
        router.add_api_route(
            f"/{route}",
            cls._create_object_wrapper(scopes, cls.__read_class__, cls.__update_class__),
            methods=["POST"],
            response_model=cls.__read_class__,
            status_code=status.HTTP_201_CREATED,
            name=f"Create {cls.__name__.replace("DB", "")} by ID",
            description=f"Creates a single object of type {cls.__name__}",
        )

    @classmethod
    def register_update(cls, *, router: APIRouter, route: str, scopes: list[str]):
        router.add_api_route(
            f"/{route}",
            cls._update_object_wrapper(scopes, cls.__read_class__, cls.__update_class__),
            methods=["PATCH"],
            response_model=cls.__read_class__,
            name=f"Update {cls.__name__.replace("DB", "")}",
            description=f"Updates a single object of type {cls.__name__}",
        )

    @classmethod
    def register_delete(cls, *, router: APIRouter, route: str, scopes: list[str]):
        router.add_api_route(
            f"/{route}",
            cls._delete_object_wrapper(scopes),
            methods=["DELETE"],
            status_code=status.HTTP_204_NO_CONTENT,
            name=f"Delete {cls.__name__.replace("DB", "")}",
            description=f"Deletes a single object of type {cls.__name__}",
        )

    @classmethod
    def register_routes(
        cls, *, router: APIRouter, route: str, read: list[str], write: list[str]
    ):
        cls.register_read_single(router=router, route=route, scopes=read)
        cls.register_read_list(router=router, route=route, scopes=read)
        cls.register_create(router=router, route=route, scopes=write)
        cls.register_update(router=router, route=route, scopes=write)
        cls.register_delete(router=router, rotue=route, scopes=write)

    @classmethod
    def _base_read_list_object(
        cls: type[Self],
        session: Session,
        offset: int,
        limit: int,
        sort: Optional[str],
        direction: Literal["asc", "desc"],
        filter: Optional[str],
        read_class: type[BaseRead],
    ) -> Any:
        query = select(cls)
        if filter:
            query = cls.apply_filter(query, filter)

        query = query.offset(offset).limit(limit)
        if sort:
            query = query.order_by(getattr(col(getattr(cls, sort)), direction)())

        count = session.exec(select(func.count()).select_from(query.subquery())).one()
        objects = session.exec(query).all()

        objects = list(map(read_class.from_db, objects))

        return PaginatedResponse(total=count, data=objects)

    @classmethod
    def _read_list_object_wrapper(cls, scopes: list[str], read_class: type[BaseRead]):
        class_vars = cls._class_vars()
        sort_options = tuple(class_vars)

        def read_list_object(
            *,
            current_user=Security(get_current_active_user, scopes=scopes),
            session: Session = Depends(get_session),
            offset: int = 0,
            limit: int = 100,
            # We can ignore the error here as it still compiles without issue
            # This is blatently incorrect usage of the Literal arg, but FastAPI doesn't provide dynamic type annotations :(
            sort: Literal[sort_options],  # type: ignore
            direction: Literal["asc", "desc"],
            filter: Optional[str] = Query(default=None, alias="query"),
        ) -> PaginatedResponse[read_class]:
            return cls._base_read_list_object(
                session, offset, limit, sort, direction, filter, read_class
            )

        return read_list_object

    @classmethod
    def _base_read_single(
        cls: type[Self],
        *,
        session: Session,
        read_class: type[BaseRead],
        **kwargs,
    ):
        id = tuple(kwargs.values())
        obj = session.get(cls, id)
        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"DB object for {cls.__name__} with id {id} not found",
            )
        return read_class.from_db(obj)

    @classmethod
    def _read_single_object_wrapper(
        cls: type[Self], scopes: list[str], read_class: type[BaseRead]
    ):
        def read_single_object(
            *,
            current_user=Security(get_current_active_user, scopes=scopes),
            session: Session = Depends(get_session),
            **kwargs,
        ) -> read_class:
            return cls._base_read_single(session=session, read_class=read_class, **kwargs)

        new_sig = cls._create_id_signature(signature(read_single_object))
        read_single_object.__signature__ = new_sig
        return read_single_object

    @classmethod
    def _base_create_object(
        cls, session: Session, raw_obj: BaseCreate, read_class: type[BaseRead]
    ):
        obj = cls.to_db(raw_obj.model_dump())
        valid_object, error = obj.validate()
        if not valid_object:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error)

        obj_id = obj._as_id_tuple()
        try:
            existing = session.get(cls, obj_id)
            if existing:
                raise Exception()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"DB Object already exists: {obj_id}",
            ) from e

        session.add(obj)
        session.commit()
        session.refresh()
        return read_class.from_db(obj)

    @classmethod
    def _create_object_wrapper(
        cls, scopes: list[str], read_class: type[BaseRead], create_class: type[BaseCreate]
    ):
        def create_object(
            *,
            current_user=Security(get_current_active_user, scopes=scopes),
            session: Session = Depends(get_session),
            obj: create_class,
        ) -> read_class:
            return cls._base_create_object(session, obj, read_class)

        return create_object

    @classmethod
    def _base_update_object(
        cls, session: Session, read_class: type[BaseRead], new_obj: BaseUpdate, **kwargs
    ):
        id = tuple(kwargs.values())
        obj = session.get(cls, id)
        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Object for {cls.__name__} with ID {id} not found",
            )

        parsed_obj = cls.to_db(new_obj.model_dump())
        for k, v in parsed_obj.model_dump().items():
            setattr(obj, k, v)

        valid_obj, error = obj.validate()
        if not valid_obj:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error)

        session.add(obj)
        session.commit()
        session.refresh(obj)
        return read_class.from_db(obj)

    @classmethod
    def _update_object_wrapper(
        cls, scopes: list[str], read_class: type[BaseRead], update_class: type[BaseUpdate]
    ):
        def update_object(
            *,
            current_user=Security(get_current_active_user, scopes=scopes),
            session: Session = Depends(get_session),
            obj: update_class,
            **kwargs,
        ) -> read_class:
            return cls._base_update_object(session, read_class, obj, **kwargs)

        new_sig = cls._create_id_signature(signature(update_object))
        update_object.__signature__ = new_sig
        return update_object

    @classmethod
    def _base_delete_object(cls, session: Session, **kwargs):
        id = tuple(kwargs.values())
        obj = session.get(cls, id)
        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Object for {cls.__name__} with ID {id} not found",
            )
        session.delete(obj)
        session.commit()
        return

    @classmethod
    def _delete_object_wrapper(cls, scopes: list[str]):
        def delete_object(
            *,
            current_user=Security(get_current_active_user, scopes=scopes),
            session: Session = Depends(get_session),
            **kwargs,
        ) -> None:
            cls._base_delete_object(session, **kwargs)

        new_sig = cls._create_id_signature(signature(delete_object))
        delete_object.__signature__ = new_sig
        return delete_object
