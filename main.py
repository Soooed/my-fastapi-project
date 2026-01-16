from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import schemas
from database import SessionLocal

app = FastAPI()

# Глобальный обработчик ошибок валидации
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

# GET /users - Получить пользователей с пагинацией и поиском
@app.get("/users")
def get_users(
    skip: int = 0,           # Пропустить первых N
    limit: int = 100,        # Вернуть не больше N
    search: Optional[str] = None,  # Поиск по имени/email
    db: Session = Depends(get_db)
):
    """Получить пользователей с пагинацией и поиском"""
    try:
        query = "SELECT * FROM users"
        params = {}
        
        # Добавляем поиск если есть
        if search:
            query += " WHERE username ILIKE :search OR email ILIKE :search"
            params["search"] = f"%{search}%"
        
        # Добавляем сортировку и пагинацию
        query += " ORDER BY id LIMIT :limit OFFSET :skip"
        params["limit"] = limit
        params["skip"] = skip
        
        result = db.execute(text(query), params)
        rows = result.fetchall()
        
        # Общее количество (для пагинации)
        count_query = "SELECT COUNT(*) FROM users"
        if search:
            count_query += " WHERE username ILIKE :search OR email ILIKE :search"
        
        total = db.execute(text(count_query), params).scalar()
        
        users = []
        for row in rows:
            users.append({
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "created_at": str(row[3]) if row[3] else None
            })
        
        return {
            "users": users,
            "count": len(users),
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": (skip + len(users)) < total
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching users: {str(e)}"
        )

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

@app.post("/users")
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
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при создании пользователя: {str(e)}"
        )

@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    """Удалить пользователя по ID"""
    try:
        # Сначала проверяем, существует ли пользователь
        existing = db.execute(
            text("SELECT id FROM users WHERE id = :id"),
            {"id": user_id}
        ).fetchone()
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {user_id} not found"
            )
        
        # Удаляем
        result = db.execute(
            text("DELETE FROM users WHERE id = :id RETURNING id"),
            {"id": user_id}
        )
        db.commit()
        
        deleted_id = result.fetchone()
        if deleted_id:
            return {"message": f"User {user_id} deleted successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete user"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting user: {str(e)}"
        )

@app.patch("/users/{user_id}", response_model=schemas.UserResponse)
def update_user(
    user_id: int, 
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db)
):
    """Обновить данные пользователя (частично)"""
    try:
        # Проверяем существование пользователя
        existing = db.execute(
            text("SELECT * FROM users WHERE id = :id"),
            {"id": user_id}
        ).fetchone()
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {user_id} not found"
            )
        
        # Собираем только переданные поля для обновления
        update_data = {}
        if user_update.username is not None:
            update_data["username"] = str(user_update.username)
        if user_update.email is not None:
            update_data["email"] = str(user_update.email)
        
        # Если ничего не передали для обновления
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No data provided for update"
            )
        
        # Проверяем уникальность новых данных (если меняем)
        if "username" in update_data or "email" in update_data:
            check_query = "SELECT id FROM users WHERE "
            check_params = {"id": user_id}
            
            conditions = []
            if "username" in update_data:
                conditions.append("(username = :new_username AND id != :id)")
                check_params["new_username"] = update_data["username"]
            if "email" in update_data:
                conditions.append("(email = :new_email AND id != :id)")
                check_params["new_email"] = update_data["email"]
            
            check_query += " OR ".join(conditions)
            conflict = db.execute(text(check_query), check_params).fetchone()
            
            if conflict:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username or email already taken by another user"
                )
        
        # Формируем SQL запрос для обновления
        set_clause = ", ".join([f"{key} = :{key}" for key in update_data.keys()])
        update_query = f"""
            UPDATE users 
            SET {set_clause}
            WHERE id = :id
            RETURNING id, username, email, created_at
        """
        
        params = {**update_data, "id": user_id}
        result = db.execute(text(update_query), params)
        db.commit()
        
        updated_row = result.fetchone()
        if not updated_row:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user"
            )
        
        return {
            "id": updated_row[0],
            "username": updated_row[1],
            "email": updated_row[2],
            "created_at": updated_row[3]
        }
            
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating user: {str(e)}"
        )