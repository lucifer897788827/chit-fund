from app.core.database import Base, engine
from app.models import *  # noqa: F401,F403


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully.")
