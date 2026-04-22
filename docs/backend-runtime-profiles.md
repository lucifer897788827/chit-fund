# Backend Runtime Profiles

`APP_ENV` now drives a small set of profile defaults while still allowing explicit env overrides to win.

## Profiles

- `production` is the default when `APP_ENV` is unset.
- `development`, `dev`, and `local` all normalize to the development profile.

## Default behavior

- Logging is structured in production and plain text in development.
- SQLAlchemy uses larger pools in production and a minimal pool in development.
- Redis connection pools use a larger connection cap in production and a smaller cap in development.
- Celery runs eagerly in development and uses normal async execution in production unless overridden.
- API pagination defaults are larger in production and smaller in development.

## Override rule

Any explicit env var still wins over the profile default. For example, setting `STRUCTURED_LOGGING=false` or `CELERY_TASK_ALWAYS_EAGER=false` will override the profile behavior.
