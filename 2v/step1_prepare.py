"""
- FP16 (half precision)  RTX 4090
CUDA_VISIBLE_DEVICES
- Нормализация  один для cosine/inner product
"""

import os
import time
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import faiss
from sentence_transformers import SentenceTransformer

import config



# GPU / Runtime settings
# ================

def _set_gpu_visibility():
    """
    Позволяет зафиксировать конкретную GPU.
    Варианты
      - выставить GPU_ID в config.py
      -или экспортировать CUDA_VISIBLE_DEVICES перед запуском
    """
    # Если уже выставил CUDA_VISIBLE_DEVICES снаружи не трогаем.
    if os.environ.get("CUDA_VISIBLE_DEVICES") is not None:
        return

    # Если в config есть GPU_ID юзаем
    gpu_id = getattr(config, "GPU_ID", None)
    if gpu_id is not None:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)


def _get_device():

    
    return "cuda" if torch.cuda.is_available() else "cpu"


def _print_gpu_info():
    if not torch.cuda.is_available():
        print("GPU не найден, используем cpu")
        return

    props = torch.cuda.get_device_properties(0)
    total_gb = props.total_memory / (1024 ** 3)
    print(f"GPU: {props.name}")
    print(f"   VRAM: {total_gb:.1f} GB")
    try:
        free, total = torch.cuda.mem_get_info()
        print(f"   Free VRAM: {free / (1024 ** 3):.2f} GB / {total / (1024 ** 3):.2f} GB")
    except Exception:
        pass



# Data load
# =====================

def load_data():
    
    print("=" * 79)
    print("ЗАГРУЗКА ДАННЫХ")
    print("=" * 79)

    # Загрузка отзывов
    print(f"\nЗагрузка отзывов из {config.REVIEWS_FILE}...")
    reviews = pd.read_csv(config.REVIEWS_FILE)

    # Определяем колонку с текстом
    if config.TEXT_COLUMN in reviews.columns:
        text_col = config.TEXT_COLUMN
    elif 'text' in reviews.columns:
        text_col = 'review_text'
    else:
        # Берём первую object-колонку как fallback
        obj_cols = reviews.columns[reviews.dtypes == 'object'].tolist()
        if not obj_cols:
            raise ValueError("Не найдено текстовых колонок (dtype=object). Укажи TEXT_COLUMN в config.py")
        text_col = obj_cols[0]
        print(f"WARN: TEXT_COLUMN не найден, используем колонку: {text_col}")

    print(f"Загружено отзывов: {len(reviews):,}")

    
    print(f"\nЗагрузка заведений из {config.PLACES_FILE}...")
    places = pd.read_csv(config.PLACES_FILE)
    print(f"Загружено заведений: {len(places):,}")

    # Базовая очистка
    print("\nБазовая фильтрация...")
    reviews[text_col] = reviews[text_col].fillna('')
    initial_count = len(reviews)
    reviews = reviews[reviews[text_col].str.len() > 10].copy()
    removed = initial_count - len(reviews)

    if removed > 0:
        print(f"   Удалено коротких отзывов: {removed:,}")

    print(f"   Финальное количество: {len(reviews):,}")


    return reviews, places, text_col



# Embeddings (GPU)
#======================

def _load_model():
    """Загрузка модели с GPU/FP16"""
    print(f"\nЗагрузка модели: {config.MODEL_NAME}")
    print("   (Первый раз займет время для скачивания модели)")

    device = _get_device()
    print(f"Используем устройство: {device}")
    _print_gpu_info()

    start_time = time.time()
    model = SentenceTransformer(config.MODEL_NAME, device=device)
    load_time = time.time() - start_time

    # FP16 на GPU даёт большой прирост. На CPU half может навредить  включаем только на CUDA
    use_fp16 = bool(getattr(config, "USE_FP16", True))
    if device == "cuda" and use_fp16:
        model = model.half()
        print("FP16 включён (model.half())")

    print(f"Модель загружена за {load_time:.1f} сек")
    print(f"   Размерность эмбеддингов: {model.get_sentence_embedding_dimension()}")
    print(f"   Устройство модели: {model.device}")


    return model


def create_embeddings(reviews, text_col):
    print("\n" + "=" * 80)
    print("СОЗДАНИЕ ЭМБЕДДИНГОВ (GPU)")
    print("=" * 81)

    # Проверка кэша
    if config.EMBEDDINGS_CACHE.exists():
        print(f"\nНайден кэш: {config.EMBEDDINGS_CACHE}")
        response = input("   Загрузить из кэша? (y/n): ").lower().strip()

        if response == 'y':
            print("   Загрузка из кэша...")
            with open(config.EMBEDDINGS_CACHE, 'rb') as f:
                embeddings = pickle.load(f)
            print(f"Загружено {len(embeddings):,} эмбеддингов из кэша")

            return embeddings
        

    
    model = _load_model()

    # Подготовка текстов
    print(f"\nПодготовка {len(reviews):,} текстов...")
    texts = reviews[text_col].astype(str).tolist()

    # Batch size: если не задан подберём разумный дефолт под 4090
    batch_size = int(getattr(config, "BATCH_SIZE", 256))
    if _get_device() == "cuda" and batch_size < 256:
        print(f"WARN: BATCH_SIZE={batch_size}, для RTX 4090 обычно лучше 512-1024")
    print(f"   Batch size: {batch_size}")

    # Создание эмбеддингов
    print("\nСоздание эмбеддингов...")
    start_time = time.time()

    # convert_to_numpy=True- возвращает embeddings на CPU (numpy), удобно для faiss-cpu
    # normalize_embeddings=False -нормализуем позже одним проходом через faiss.normalize_L2
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=False
    )

    elapsed = time.time() - start_time

    # Логи по памяти
    if _get_device() == "cuda":
        try:
            max_mem = torch.cuda.max_memory_allocated() / (1024 ** 3)
            print(f"Max GPU memory allocated: {max_mem:.2f} GB")
        except Exception:
            pass

    print(f"\nЭмбеддинги созданы за {elapsed / 60:.1f} минут")
    print(f"   Размер: {embeddings.shape}")
    print(f"   dtype: {embeddings.dtype}")
    print(f"   Память: {embeddings.nbytes / (1024**2):.1f} MB")

    # Сохранение в кэш
    print(f"\nСохранение в кэш: {config.EMBEDDINGS_CACHE}")
    with open(config.EMBEDDINGS_CACHE, 'wb') as f:
        pickle.dump(embeddings, f)

    print("Сохранено")


    return embeddings


# =========================
# FAISS index (CPU)


def build_faiss_index(embeddings):
    """Построение FAISS индекса (CPU). Для 73k векторов этого более чем достаточно."""
    print("\n" + "=" * 80)
    print("ПОСТРОЕНИЕ FAISS ИНДЕКСА (CPU)")
    print("=" * 80)

    # Проверка кэша
    if config.INDEX_CACHE.exists():
        print(f"\nНайден кэш: {config.INDEX_CACHE}")
        response = input("   Загрузить из кэша? (y/n): ").lower().strip()

        if response == 'y':
            print("   Загрузка из кэша...")
            index = faiss.read_index(str(config.INDEX_CACHE))
            print(f"Индекс загружен: {index.ntotal:,} векторов")
            return index

    print(f"\nПостроение индекса для {len(embeddings):,} векторов...")

    # FAISS любит float32
    if embeddings.dtype != np.float32:
        embeddings = embeddings.astype(np.float32, copy=False)

    dimension = embeddings.shape[1]
    num_vectors = len(embeddings)

    print(f"   Размерность: {dimension}")
    print(f"   Количество векторов: {num_vectors:,}")

    # Нормализация для косинусного сходства:
    # Косинус = inner product при L2-нормированных векторах.
    print("\n   Нормализация векторов (L2) для cosine similarity...")
    faiss.normalize_L2(embeddings)

    # Выбор типа индекса
    if num_vectors < 100000:
        print("\n   Используем IndexFlatIP (точный поиск, cosine через IP)")
        index = faiss.IndexFlatIP(dimension)
    else:
        print("\n   Используем IndexIVFFlat (приближенный поиск)")
        nlist = int(getattr(config, "IVF_NLIST", 100))
        quantizer = faiss.IndexFlatIP(dimension)
        index = faiss.IndexIVFFlat(quantizer, dimension, nlist)

        print("   Обучение индекса...")
        index.train(embeddings)

    # Добавление векторов
    print("   Добавление векторов в индекс...")
    index.add(embeddings)

    print(f"\nИндекс построен: {index.ntotal:,} векторов")

    # Сохранение
    print(f"\nСохранение в кэш: {config.INDEX_CACHE}")
    faiss.write_index(index, str(config.INDEX_CACHE))
    print("Сохранено")

    return index


# ========================
# Metadata

def save_metadata(reviews, places, text_col):
    print("\n" + "=" * 80)
    print("СОХРАНЕНИЕ МЕТАДАННЫХ")
    print("=" * 80)

    metadata = {
        'reviews': reviews,
        'places': places,
        'text_column': text_col,
        'total_reviews': len(reviews),
        'total_places': len(places),
        'model_name': config.MODEL_NAME,
        'device': _get_device(),
        'use_fp16': bool(getattr(config, "USE_FP16", True))
    }

    print(f"\nСохранение в: {config.METADATA_CACHE}")
    with open(config.METADATA_CACHE, 'wb') as f:
        pickle.dump(metadata, f)

    print("Метаданные сохранены")



# Main
# =========================

def main():
    """Главная функция"""
    _set_gpu_visibility()

    print("\n" + "=" * 80)
    print("ПОДГОТОВКА ДАННЫХ ДЛЯ SEMANTIC SEARCH (GPU)")
    print("=" * 80)
    print("\nЭтот скрипт:")
    print("  1. Загрузит ваши данные")
    print("  2. Создаст эмбеддинги для всех отзывов (GPU/FP16 если доступно)")
    print("  3. Построит FAISS индекс для быстрого поиска (CPU)")
    print("  4. Сохранит всё в cache/ для повторного использования")
    print("\nНа RTX 4090 обычно это занимает 2-6 минут для ~70k отзывов")
    print("   Последующие запуски будут мгновенными (используется кэш)")
    print("\n" + "=" * 80)

    input("\nНажмите Enter для продолжения...")

    try:
        # Шаг 1: Загрузка данных
        reviews, places, text_col = load_data()

        # Шаг 2: Создание эмбеддингов (GPU)
        embeddings = create_embeddings(reviews, text_col)

        # Шаг 3: Построение индекса (CPU)
        index = build_faiss_index(embeddings)

        # Шаг 4: Сохранение метаданных
        save_metadata(reviews, places, text_col)

        # Финальная статистика
        print("\n" + "=" * 80)
        print("ПОДГОТОВКА ЗАВЕРШЕНА")
        print("=" * 80)

        print(f"\nСтатистика:")
        print(f"   Отзывов обработано: {len(reviews):,}")
        print(f"   Заведений в базе: {len(places):,}")
        print(f"   Эмбеддингов создано: {len(embeddings):,}")
        print(f"   Векторов в индексе: {index.ntotal:,}")

        print(f"\nФайлы сохранены в: {config.CACHE_DIR}")
        print(f"   - {config.EMBEDDINGS_CACHE.name}")
        print(f"   - {config.INDEX_CACHE.name}")
        print(f"   - {config.METADATA_CACHE.name}")

        cache_size = sum(
            f.stat().st_size for f in config.CACHE_DIR.glob('*') if f.is_file()
        ) / (1024**2)
        print(f"\n   Общий размер кэша: {cache_size:.1f} MB")

        print("\nТеперь можно запустить поиск:")
        print("   python step2_search.py")
        print("   или")
        print("   streamlit run app.py")

    except FileNotFoundError as e:
        print(f"\nОшибка: Файл не найден")
        print(f"   {e}")
        print("\nПроверьте, что файлы данных находятся в:")
        print(f"   {config.DATA_DIR}")

    except Exception as e:
        print(f"\nОшибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
