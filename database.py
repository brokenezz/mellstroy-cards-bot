import asyncpg
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta
import logging
from config import DATABASE_URL
from models import User, Card, UserCard, Rarity

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Создание пула соединений"""
        self.pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)
        await self.create_tables()
        logger.info("Database connected")
    
    async def create_tables(self):
        """Создание таблиц"""
        async with self.pool.acquire() as conn:
            # Таблица пользователей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    username TEXT,
                    level INT DEFAULT 1,
                    exp INT DEFAULT 0,
                    cards_count INT DEFAULT 0,
                    total_finds INT DEFAULT 0,
                    daily_bonus_date DATE,
                    is_premium BOOLEAN DEFAULT FALSE,
                    premium_until TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Таблица карточек
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS cards (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    rarity TEXT CHECK (rarity IN ('common', 'rare', 'epic', 'legendary')),
                    image_url TEXT NOT NULL,
                    description TEXT,
                    video_url TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Коллекция пользователей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_cards (
                    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                    card_id INT REFERENCES cards(id) ON DELETE CASCADE,
                    count INT DEFAULT 1,
                    first_found TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (user_id, card_id)
                )
            """)
            
            # Лента находок
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS finds_log (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(id),
                    card_id INT REFERENCES cards(id),
                    found_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Проверяем, есть ли карточки в БД
            count = await conn.fetchval("SELECT COUNT(*) FROM cards")
            if count == 0:
                await self.insert_sample_cards()
    
    async def insert_sample_cards(self):
        """Добавление примеров карточек"""
        sample_cards = [
            ("Мем 'Я ебу?'", Rarity.COMMON, "https://i.imgur.com/placeholder1.jpg", "Классическая фраза Mellstroy"),
            ("Кривой стрим", Rarity.COMMON, "https://i.imgur.com/placeholder2.jpg", "Один из первых стримов"),
            ("Ламборгини", Rarity.RARE, "https://i.imgur.com/placeholder3.jpg", "Мечта Mellstroy"),
            ("Фраза 'Пон'", Rarity.RARE, "https://i.imgur.com/placeholder4.jpg", "Культовая фраза"),
            ("Король стримов", Rarity.EPIC, "https://i.imgur.com/placeholder5.jpg", "Пик популярности"),
            ("Легендарный момент", Rarity.LEGENDARY, "https://i.imgur.com/placeholder6.jpg", "Исторический момент на стриме"),
            ("Коллаба с известным стримером", Rarity.EPIC, "https://i.imgur.com/placeholder7.jpg", "Совместный стрим"),
            ("Миллион подписчиков", Rarity.LEGENDARY, "https://i.imgur.com/placeholder8.jpg", "Юбилейная карточка"),
        ]
        
        async with self.pool.acquire() as conn:
            for name, rarity, url, desc in sample_cards:
                await conn.execute("""
                    INSERT INTO cards (name, rarity, image_url, description)
                    VALUES ($1, $2, $3, $4)
                """, name, rarity.value, url, desc)
        
        logger.info("Sample cards inserted")
    
    # === User methods ===
    async def get_user(self, user_id: int) -> Optional[User]:
        """Получение пользователя"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM users WHERE id = $1
            """, user_id)
            
            if row:
                return User(
                    id=row['id'],
                    username=row['username'],
                    level=row['level'],
                    exp=row['exp'],
                    cards_count=row['cards_count'],
                    total_finds=row['total_finds'],
                    daily_bonus_date=row['daily_bonus_date'],
                    is_premium=row['is_premium'],
                    premium_until=row['premium_until'],
                    created_at=row['created_at']
                )
            return None
    
    async def create_user(self, user_id: int, username: Optional[str]) -> User:
        """Создание нового пользователя"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (id, username)
                VALUES ($1, $2)
                ON CONFLICT (id) DO NOTHING
            """, user_id, username)
            
            return await self.get_user(user_id)
    
    async def update_user_exp(self, user_id: int, exp_gain: int) -> tuple[int, bool]:
        """Обновление опыта и уровней"""
        async with self.pool.acquire() as conn:
            user = await self.get_user(user_id)
            if not user:
                return user.level, False
            
            new_exp = user.exp + exp_gain
            level_up = False
            new_level = user.level
            
            while new_exp >= new_level * 100:
                new_exp -= new_level * 100
                new_level += 1
                level_up = True
            
            await conn.execute("""
                UPDATE users 
                SET exp = $1, level = $2
                WHERE id = $3
            """, new_exp, new_level, user_id)
            
            return new_level, level_up
    
    async def update_stats(self, user_id: int, card_found: bool = True):
        """Обновление статистики"""
        async with self.pool.acquire() as conn:
            if card_found:
                await conn.execute("""
                    UPDATE users 
                    SET cards_count = cards_count + 1,
                        total_finds = total_finds + 1
                    WHERE id = $1
                """, user_id)
    
    # === Cards methods ===
    async def get_random_card(self, is_premium: bool = False) -> Optional[Card]:
        """Получение случайной карточки с учетом редкости"""
        import random
        
        # Выбираем редкость
        rarities = list(Rarity)
        weights = [r.chance for r in rarities]
        
        # Для премиум пользователей шанс легендарки выше
        if is_premium:
            weights[3] = 0.08  # legendary
            weights[2] = 0.14  # epic
            weights[1] = 0.23  # rare
            weights[0] = 0.55  # common
        
        selected_rarity = random.choices(rarities, weights=weights)[0]
        
        # Получаем карточку выбранной редкости
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM cards 
                WHERE rarity = $1
                ORDER BY RANDOM()
                LIMIT 1
            """, selected_rarity.value)
            
            if row:
                return Card(
                    id=row['id'],
                    name=row['name'],
                    rarity=Rarity(row['rarity']),
                    image_url=row['image_url'],
                    description=row['description'],
                    video_url=row['video_url']
                )
        return None
    
    async def add_card_to_user(self, user_id: int, card_id: int) -> int:
        """Добавление карточки пользователю"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO user_cards (user_id, card_id)
                VALUES ($1, $2)
                ON CONFLICT (user_id, card_id) 
                DO UPDATE SET count = user_cards.count + 1
                RETURNING count
            """, user_id, card_id)
            
            # Логируем находку
            await conn.execute("""
                INSERT INTO finds_log (user_id, card_id)
                VALUES ($1, $2)
            """, user_id, card_id)
            
            return result['count'] if result else 1
    
    async def get_user_cards(self, user_id: int, limit: int = 50, offset: int = 0) -> List[UserCard]:
        """Получение коллекции пользователя"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT c.id, c.name, c.rarity, c.image_url, uc.count
                FROM user_cards uc
                JOIN cards c ON uc.card_id = c.id
                WHERE uc.user_id = $1
                ORDER BY 
                    CASE c.rarity
                        WHEN 'legendary' THEN 4
                        WHEN 'epic' THEN 3
                        WHEN 'rare' THEN 2
                        WHEN 'common' THEN 1
                    END DESC,
                    c.name
                LIMIT $2 OFFSET $3
            """, user_id, limit, offset)
            
            return [
                UserCard(
                    card_id=row['id'],
                    name=row['name'],
                    rarity=Rarity(row['rarity']),
                    count=row['count'],
                    image_url=row['image_url']
                )
                for row in rows
            ]
    
    async def get_total_cards_count(self) -> int:
        """Общее количество карточек в игре"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM cards")
    
    async def get_user_cards_count(self, user_id: int) -> int:
        """Количество уникальных карточек у пользователя"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval("""
                SELECT COUNT(*) FROM user_cards WHERE user_id = $1
            """, user_id)
    
    # === Bonus methods ===
    async def can_claim_daily_bonus(self, user_id: int) -> bool:
        """Проверка, можно ли получить ежедневный бонус"""
        async with self.pool.acquire() as conn:
            last_bonus = await conn.fetchval("""
                SELECT daily_bonus_date FROM users WHERE id = $1
            """, user_id)
            
            if not last_bonus:
                return True
            return last_bonus < date.today()
    
    async def claim_daily_bonus(self, user_id: int, bonus_amount: int) -> bool:
        """Получение ежедневного бонуса"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE users 
                SET daily_bonus_date = $1,
                    cards_count = cards_count + $2
                WHERE id = $3
            """, date.today(), bonus_amount, user_id)
            return True
    
    # === Premium methods ===
    async def set_premium(self, user_id: int, days: int):
        """Установка премиум статуса"""
        async with self.pool.acquire() as conn:
            until = datetime.now() + timedelta(days=days)
            await conn.execute("""
                UPDATE users 
                SET is_premium = TRUE, premium_until = $1
                WHERE id = $2
            """, until, user_id)
    
    async def check_premium_expired(self, user_id: int):
        """Проверка истечения премиума"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval("""
                UPDATE users 
                SET is_premium = FALSE 
                WHERE id = $1 AND premium_until < NOW() AND is_premium = TRUE
                RETURNING id
            """, user_id)
            return result is not None
    
    # === Rating methods ===
    async def get_top_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение топа пользователей"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, username, level, cards_count, total_finds
                FROM users
                ORDER BY cards_count DESC, level DESC
                LIMIT $1
            """, limit)
            
            return [dict(row) for row in rows]
    
    # === Admin methods ===
    async def get_all_cards(self) -> List[Card]:
        """Получение всех карточек (для админа)"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM cards ORDER BY id")
            return [
                Card(
                    id=row['id'],
                    name=row['name'],
                    rarity=Rarity(row['rarity']),
                    image_url=row['image_url'],
                    description=row['description'],
                    video_url=row['video_url']
                )
                for row in rows
            ]
    
    async def add_card(self, name: str, rarity: Rarity, image_url: str, description: str, video_url: str = None) -> int:
        """Добавление новой карточки"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval("""
                INSERT INTO cards (name, rarity, image_url, description, video_url)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            """, name, rarity.value, image_url, description, video_url)

# Создаем глобальный экземпляр
db = Database()