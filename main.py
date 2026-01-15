from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from sqlalchemy import text
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import ValidationError
import schemas

app = FastAPI()

# Глобальный обработчик ошибок валидации
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Ошибка валидации",
            "errors": exc.errors()
        },
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

# Dependency для получения сессии БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Проверка подключения к БД"""
    try:
        # Простейший запрос к БД
        result = db.execute(text("SELECT version()"))
        db_version = result.scalar()
        return {
            "status": "healthy",
            "database": "connected",
            "postgres_version": db_version
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }

@app.get("/users")
def get_users(db: Session = Depends(get_db)):
    """Получить всех пользователей"""
    try:
        result = db.execute(text("SELECT * FROM users ORDER BY id"))
        rows = result.fetchall()
        
        users = []
        for row in rows:
            if row:  # ПРОВЕРКА ДЛЯ КАЖДОЙ СТРОКИ
                users.append({
                    "id": row[0],
                    "username": row[1],
                    "email": row[2],
                    "created_at": str(row[3]) if row[3] else None
                })
        
        return {"users": users, "count": len(users)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Получить одного пользователя по ID"""
    try:
        result = db.execute(
            text("SELECT * FROM users WHERE id = :id"),
            {"id": user_id}
        )
        row = result.fetchone()
        
        if not row:  # ПРОВЕРКА!
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "created_at": str(row[3]) if row[3] else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/users/create")
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Создать пользователя с валидацией"""
    try:
        # Проверяем, не существует ли уже пользователь
        existing = db.execute(
            text("SELECT id FROM users WHERE username = :username OR email = :email"),
            {"username": user.username, "email": user.email}
        ).fetchone()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пользователь с таким именем или email уже существует"
            )
        
        # Создаем пользователя
        result = db.execute(
            text("""
                INSERT INTO users (username, email) 
                VALUES (:username, :email)
                RETURNING id, username, email, created_at
            """),
            {"username": user.username, "email": user.email}
        )
        db.commit()
        
        row = result.fetchone()
        
        # ПРОВЕРКА НА НЕОБХОДИМОСТЬ!
        if not row:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось создать пользователя"
            )
        
        return {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "created_at": row[3]
        }
        
    except HTTPException:
        raise  # Пробрасываем HTTPException дальше
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при создании пользователя: {str(e)}"
        )