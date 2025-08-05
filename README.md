# Library API

A FastAPI library management system with SQLAlchemy and Alembic.

## Quick Start

1. **Setup**:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. **Run**:
```bash
uvicorn main:app --reload
# or
./venv/bin/python -m uvicorn main:app --reload
```

3. **Access**:
- API: `http://127.0.0.1:8000`
- Docs: `http://127.0.0.1:8000/docs`

## Database

```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

## Tech Stack

- FastAPI
- SQLAlchemy
- Alembic
- Python 3.8+

3. **WorkFlow**:

# 1. Develop your app normally
python -m uvicorn app.main:app --reload
# 2. When you change models, create migration
alembic revision --autogenerate -m "Add email verification"
# 3. Apply the migration
alembic upgrade head
# 4. Continue developing
python -m uvicorn app.main:app --reload

# See current migration version
alembic current
# See if there are pending migrations
alembic heads  # Shows latest available
alembic current  # Shows what's applied
# If they're different, you need to upgrade
alembic upgrade head