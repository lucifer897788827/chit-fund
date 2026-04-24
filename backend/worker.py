import logging

from app.core.celery_app import celery_app
from app.core.logging import APP_LOGGER_NAME, configure_logging

app = celery_app
logger = logging.getLogger(APP_LOGGER_NAME)


def main() -> None:
    configure_logging()
    logger.info("worker.starting", extra={"event": "worker.starting"})
    try:
        celery_app.start()
    finally:
        logger.info("worker.stopping", extra={"event": "worker.stopping"})


if __name__ == "__main__":
    main()
