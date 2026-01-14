from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from sqlalchemy import text

app = FastAPI()

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
        # Простой SQL запрос
        result = db.execute(text("SELECT * FROM users ORDER BY id"))
        rows = result.fetchall()
        
        # Преобразуем в список словарей
        users = []
        for row in rows:
            users.append({
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "created_at": str(row[3]) if row[3] else None
            })
        
        return {"users": users, "count": len(users)}
    except Exception as e:
        return {"error": str(e)}

@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Получить одного пользователя по ID"""
    try:
        result = db.execute(
            text("SELECT * FROM users WHERE id = :id"),
            {"id": user_id}
        )
        row = result.fetchone()
        
        if not row:
            return {"error": "User not found"}
        
        return {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "created_at": str(row[3]) if row[3] else None
        }
    except Exception as e:
        return {"error": str(e)}