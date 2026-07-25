# Alembic migrations

The application uses `mysql+asyncmy`; Alembic converts the same URL to the synchronous `mysql+pymysql` driver.

Commands are run from `backend/`:

```bash
alembic current
alembic upgrade head
alembic downgrade -1
alembic revision --autogenerate -m "describe change"
alembic check
```

`20260724_0001` is the only migration allowed to execute the frozen baseline SQL files. Do not edit those files after the revision has been deployed. Every later revision must contain explicit Alembic operations and follow an expand/migrate/contract rollout.

