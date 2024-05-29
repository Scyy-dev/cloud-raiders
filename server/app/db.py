from typing import Generator

from sqlmodel import Session, create_engine

engine_connection_string = ""
engine = create_engine(engine_connection_string)

def get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session
