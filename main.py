from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship

# 1. Инициализация базы данных SQLite (создаст файл rpg_game.db)
DATABASE_URL = "sqlite:///./rpg_game.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# === ТАБЛИЦЫ БАЗЫ ДАННЫХ (SQLAlchemy) ===

# Главный герой (его характеристики и ресурсы)
class HeroDB(Base):
    __tablename__ = "hero"
    id = Column(Integer, primary_key=True, index=True)
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)
    xp_to_next_level = Column(Integer, default=100)
    gold = Column(Integer, default=0)
    strength = Column(Integer, default=10)
    intellect = Column(Integer, default=10)
    agility = Column(Integer, default=10)

# Игровые категории квестов
class CategoryDB(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    stat_reward = Column(String)  # strength, intellect, agility
    xp_reward = Column(Integer)   # Опыт за выполнение
    gold_reward = Column(Integer) # Золото за выполнение

    tasks = relationship("TaskDB", back_populates="category", cascade="all, delete-orphan")

# Сами квесты (задачи)
class TaskDB(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    done = Column(Boolean, default=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    
    category = relationship("CategoryDB", back_populates="tasks")

# Товары в Лавке Наград
class ShopItemDB(Base):
    __tablename__ = "shop_items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    cost = Column(Integer)

# Создаем все таблицы в файле базы данных
Base.metadata.create_all(bind=engine)

# Наполняем стартовый мир игры, если база пустая
db = SessionLocal()
if db.query(HeroDB).count() == 0:
    db.add(HeroDB(id=1)) # Создаем персонажа
if db.query(CategoryDB).count() == 0:
    db.add(CategoryDB(name="Учеба 🧠", stat_reward="intellect", xp_reward=30, gold_reward=15))
    db.add(CategoryDB(name="Спорт и Дом 💪", stat_reward="strength", xp_reward=25, gold_reward=10))
    db.add(CategoryDB(name="Дела и Работа ⚡", stat_reward="agility", xp_reward=35, gold_reward=20))
if db.query(ShopItemDB).count() == 0:
    db.add(ShopItemDB(name="Посмотреть серию сериала 🍿", cost=30))
    db.add(ShopItemDB(name="Съесть любимую вкусняшку 🍰", cost=45))
    db.add(ShopItemDB(name="1 час отдыха в видеоиграх 🎮", cost=60))
db.commit()
db.close()

app = FastAPI(title="RPG Task Engine v1.0")

# === СХЕМЫ ВАЛИДАЦИИ ДАННЫХ (Pydantic) ===
class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100) # Валидация длины Pydantic
    category_id: int

class BuyItemRequest(BaseModel):
    item_id: int

# Зависимость для сессий БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Раздача фронтенда
@app.get("/")
def read_root():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")

# === ЭНДПОИНТЫ ИГРОВОГО ПРОЦЕССА ===

# 1. Получить состояние героя
@app.get("/hero")
def get_hero(db: Session = Depends(get_db)):
    return db.query(HeroDB).first()

# 2. Получить список доступных категорий
@app.get("/categories")
def get_categories(db: Session = Depends(get_db)):
    return db.query(CategoryDB).all()

# 3. Посмотреть журнал активных квестов
@app.get("/tasks")
def get_tasks(db: Session = Depends(get_db)):
    tasks = db.query(TaskDB).all()
    return [{
        "id": t.id, 
        "title": t.title, 
        "done": t.done,
        "category_name": t.category.name,
        "reward_info": f"+{t.category.xp_reward}XP / +{t.category.gold_reward}G"
    } for t in tasks]

# 4. Взять новый квест (Добавить задачу)
@app.post("/tasks", status_code=201)
def create_task(task_data: TaskCreate, db: Session = Depends(get_db)):
    new_task = TaskDB(title=task_data.title, category_id=task_data.category_id)
    db.add(new_task)
    db.commit()
    return {"status": "Квест успешно занесен в журнал"}

# 5. Сдать квест (Выполнить задачу и получить награду)
@app.patch("/tasks/{task_id}")
def complete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Квест не найден")
    if task.done:
        return {"status": "Квест уже был выполнен ранее"}

    task.done = True
    hero = db.query(HeroDB).first()
    category = task.category

    # Выдаем награды за квест
    hero.xp += category.xp_reward
    hero.gold += category.gold_reward

    # Качаем нужный стат
    if category.stat_reward == "intellect": hero.intellect += 1
    elif category.stat_reward == "strength": hero.strength += 1
    elif category.stat_reward == "agility": hero.agility += 1

    # Механика Level Up [4.3]
    level_up = False
    if hero.xp >= hero.xp_to_next_level:
        hero.xp -= hero.xp_to_next_level
        hero.level += 1
        hero.xp_to_next_level = int(hero.xp_to_next_level * 1.4) # Увеличиваем сложность следующего уровня
        level_up = True

    db.commit()
    return {"status": "Квест выполнен!", "level_up": level_up}

# 6. Отменить квест (Удалить задачу без штрафа)
@app.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Квест не найден")
    db.delete(task)
    db.commit()
    return {"status": "Квест отменен"}

# 7. Посмотреть товары в лавке наград
@app.get("/shop")
def get_shop(db: Session = Depends(get_db)):
    return db.query(ShopItemDB).all()

# 8. Купить награду в лавке за золото
@app.post("/shop/buy")
def buy_reward(req: BuyItemRequest, db: Session = Depends(get_db)):
    hero = db.query(HeroDB).first()
    item = db.query(ShopItemDB).filter(ShopItemDB.id == req.item_id).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден")
    if hero.gold < item.cost:
        raise HTTPException(status_code=400, detail="Недостаточно золота! Отправляйся фармить квесты!")

    hero.gold -= item.cost
    db.commit()
    return {"message": f"Вы успешно приобрели награду: '{item.name}'!", "gold_left": hero.gold}
