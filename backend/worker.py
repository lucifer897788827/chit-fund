from app.core.celery_app import celery_app

app = celery_app


def main() -> None:
    celery_app.start()


if __name__ == "__main__":
    main()
