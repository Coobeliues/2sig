import os
from pathlib import Path


#Пути
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = BASE_DIR / "cache"

#І директории если их нет
CACHE_DIR.mkdir(exist_ok=True)

# Файлы данных
REVIEWS_FILE = DATA_DIR / "reviews_cleaned_advanced.csv"
# Fallback если продвинутой версии нет
if not REVIEWS_FILE.exists():
    REVIEWS_FILE = DATA_DIR / "reviews.csv"

PLACES_FILE = DATA_DIR / "places.csv"

#Кэш файлы
EMBEDDINGS_CACHE = CACHE_DIR / "embeddings.pkl"
INDEX_CACHE = CACHE_DIR / "faiss_index.bin"
METADATA_CACHE = CACHE_DIR / "metadata.pkl"

# Настройки модели
MODEL_NAME = "sentence-transformers/LaBSE"  #Мультияз модель

#Альтер:
# MODEL_NAME = "DeepPavlov/rubert-base-cased-sentence"  # Только русский, быстрее
# MODEL_NAME = "all-MiniLM-L6-v2"  # Легкая, быстрая

# BATCH_SIZE = 32  
# =========================
# GPU / Performance
# =========================

GPU_ID = 0          # 
USE_FP16 = True     # включать FP16 (RTX 4090 — обязательно)

# Batch size для encode (4090 спокойно держит 512–1024)
BATCH_SIZE = 768



# Настройки поиска
DEFAULT_TOP_K = 10  # Количество резов
DEFAULT_MIN_REVIEWS = 3  # Минимум релевантных отзывов для заведения
DEFAULT_AGGREGATION = "weighted"  # mean, max, weighted

# Колонки данных
TEXT_COLUMN = "text"  # Колонка с очищенным текстом (с эмодзи)
# Если не найдена, будет использована "review_text"


print("Конфигурация загружена")
print(f"   Данные: {DATA_DIR}")
print(f"   Кэш: {CACHE_DIR}")
print(f"   Модель: {MODEL_NAME}")





