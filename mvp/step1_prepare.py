"""
ШАГ 1: Подготовка данных
Создание эмбеддингов и FAISS индекса
Запускается ОДИН РАЗ! Результаты сохраняются в cache/
"""

import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import pickle
from pathlib import Path
from tqdm import tqdm
import time

import config


def load_data():
    """Загрузка данных"""
    print("=" * 80)
    print("📂 ЗАГРУЗКА ДАННЫХ")
    print("=" * 80)

    # Загрузка отзывов
    print(f"\nЗагрузка отзывов из {config.REVIEWS_FILE}...")
    reviews = pd.read_csv(config.REVIEWS_FILE)

    # Определяем колонку с текстом
    if config.TEXT_COLUMN in reviews.columns:
        text_col = config.TEXT_COLUMN
    elif 'review_text' in reviews.columns:
        text_col = 'review_text'
    else:
        text_col = reviews.columns[reviews.dtypes == 'object'][0]
        print(f"⚠️  Используем колонку: {text_col}")

    print(f"✅ Загружено отзывов: {len(reviews):,}")

    # Загрузка заведений
    print(f"\nЗагрузка заведений из {config.PLACES_FILE}...")
    places = pd.read_csv(config.PLACES_FILE)
    print(f"✅ Загружено заведений: {len(places):,}")

    # Базовая очистка
    print("\n🧹 Базовая фильтрация...")
    reviews[text_col] = reviews[text_col].fillna('')
    initial_count = len(reviews)
    reviews = reviews[reviews[text_col].str.len() > 10]
    removed = initial_count - len(reviews)

    if removed > 0:
        print(f"   Удалено коротких отзывов: {removed:,}")

    print(f"   Финальное количество: {len(reviews):,}")

    return reviews, places, text_col


def create_embeddings(reviews, text_col):
    """Создание эмбеддингов для всех отзывов"""
    print("\n" + "=" * 80)
    print("🧮 СОЗДАНИЕ ЭМБЕДДИНГОВ")
    print("=" * 80)

    # Проверка кэша
    if config.EMBEDDINGS_CACHE.exists():
        print(f"\n✨ Найден кэш: {config.EMBEDDINGS_CACHE}")
        response = input("   Загрузить из кэша? (y/n): ").lower()

        if response == 'y':
            print("   Загрузка из кэша...")
            with open(config.EMBEDDINGS_CACHE, 'rb') as f:
                embeddings = pickle.load(f)
            print(f"✅ Загружено {len(embeddings):,} эмбеддингов из кэша")
            return embeddings

    # Загрузка модели
    print(f"\n⏳ Загрузка модели: {config.MODEL_NAME}")
    print("   (Первый раз займет время для скачивания модели)")

    start_time = time.time()
    model = SentenceTransformer(config.MODEL_NAME)
    load_time = time.time() - start_time

    print(f"✅ Модель загружена за {load_time:.1f} сек")
    print(f"   Размерность эмбеддингов: {model.get_sentence_embedding_dimension()}")

    # Подготовка текстов
    print(f"\n📝 Подготовка {len(reviews):,} текстов...")
    texts = reviews[text_col].tolist()

    # Создание эмбеддингов
    print("\n⏳ Создание эмбеддингов...")
    print(f"   Это займет примерно {len(texts) * 0.05 / 60:.1f} минут на CPU")
    print("   (можно сходить попить кофе ☕)")

    start_time = time.time()

    embeddings = model.encode(
        texts,
        batch_size=config.BATCH_SIZE,
        show_progress_bar=True,
        convert_to_numpy=True
    )

    elapsed = time.time() - start_time

    print(f"\n✅ Эмбеддинги созданы за {elapsed / 60:.1f} минут")
    print(f"   Размер: {embeddings.shape}")
    print(f"   Память: {embeddings.nbytes / (1024**2):.1f} MB")

    # Сохранение в кэш
    print(f"\n💾 Сохранение в кэш: {config.EMBEDDINGS_CACHE}")
    with open(config.EMBEDDINGS_CACHE, 'wb') as f:
        pickle.dump(embeddings, f)

    print("✅ Сохранено")

    return embeddings


def build_faiss_index(embeddings):
    """Построение FAISS индекса"""
    print("\n" + "=" * 80)
    print("🏗️  ПОСТРОЕНИЕ FAISS ИНДЕКСА")
    print("=" * 80)

    # Проверка кэша
    if config.INDEX_CACHE.exists():
        print(f"\n✨ Найден кэш: {config.INDEX_CACHE}")
        response = input("   Загрузить из кэша? (y/n): ").lower()

        if response == 'y':
            print("   Загрузка из кэша...")
            index = faiss.read_index(str(config.INDEX_CACHE))
            print(f"✅ Индекс загружен: {index.ntotal:,} векторов")
            return index

    print(f"\n⏳ Построение индекса для {len(embeddings):,} векторов...")

    dimension = embeddings.shape[1]
    num_vectors = len(embeddings)

    print(f"   Размерность: {dimension}")
    print(f"   Количество векторов: {num_vectors:,}")

    # Выбор типа индекса
    if num_vectors < 100000:
        print("\n   Используем IndexFlatIP (точный поиск)")
        print("   (Для <100k векторов - оптимально)")
        index = faiss.IndexFlatIP(dimension)
    else:
        print("\n   Используем IndexIVFFlat (приближенный поиск)")
        print("   (Для >100k векторов - быстрее)")
        nlist = 100
        quantizer = faiss.IndexFlatIP(dimension)
        index = faiss.IndexIVFFlat(quantizer, dimension, nlist)

        print("   Обучение индекса...")
        index.train(embeddings)

    # Нормализация для косинусного сходства
    print("\n   Нормализация векторов...")
    faiss.normalize_L2(embeddings)

    # Добавление векторов
    print("   Добавление векторов в индекс...")
    index.add(embeddings)

    print(f"\n✅ Индекс построен: {index.ntotal:,} векторов")

    # Сохранение
    print(f"\n💾 Сохранение в кэш: {config.INDEX_CACHE}")
    faiss.write_index(index, str(config.INDEX_CACHE))
    print("✅ Сохранено")

    return index


def save_metadata(reviews, places, text_col):
    """Сохранение метаданных"""
    print("\n" + "=" * 80)
    print("💾 СОХРАНЕНИЕ МЕТАДАННЫХ")
    print("=" * 80)

    metadata = {
        'reviews': reviews,
        'places': places,
        'text_column': text_col,
        'total_reviews': len(reviews),
        'total_places': len(places),
        'model_name': config.MODEL_NAME
    }

    print(f"\nСохранение в: {config.METADATA_CACHE}")
    with open(config.METADATA_CACHE, 'wb') as f:
        pickle.dump(metadata, f)

    print("✅ Метаданные сохранены")


def main():
    """Главная функция"""
    print("\n" + "=" * 80)
    print("🚀 ПОДГОТОВКА ДАННЫХ ДЛЯ SEMANTIC SEARCH")
    print("=" * 80)
    print("\nЭтот скрипт:")
    print("  1. Загрузит ваши данные")
    print("  2. Создаст эмбеддинги для всех отзывов")
    print("  3. Построит FAISS индекс для быстрого поиска")
    print("  4. Сохранит всё в cache/ для повторного использования")
    print("\n⏱️  Это займет 30-60 минут при первом запуске")
    print("   Последующие запуски будут мгновенными (используется кэш)")
    print("\n" + "=" * 80)

    input("\nНажмите Enter для продолжения...")

    try:
        # Шаг 1: Загрузка данных
        reviews, places, text_col = load_data()

        # Шаг 2: Создание эмбеддингов
        embeddings = create_embeddings(reviews, text_col)

        # Шаг 3: Построение индекса
        index = build_faiss_index(embeddings)

        # Шаг 4: Сохранение метаданных
        save_metadata(reviews, places, text_col)

        # Финальная статистика
        print("\n" + "=" * 80)
        print("🎉 ПОДГОТОВКА ЗАВЕРШЕНА!")
        print("=" * 80)

        print(f"\n📊 Статистика:")
        print(f"   Отзывов обработано: {len(reviews):,}")
        print(f"   Заведений в базе: {len(places):,}")
        print(f"   Эмбеддингов создано: {len(embeddings):,}")
        print(f"   Векторов в индексе: {index.ntotal:,}")

        print(f"\n💾 Файлы сохранены в: {config.CACHE_DIR}")
        print(f"   - {config.EMBEDDINGS_CACHE.name}")
        print(f"   - {config.INDEX_CACHE.name}")
        print(f"   - {config.METADATA_CACHE.name}")

        cache_size = sum(
            f.stat().st_size for f in config.CACHE_DIR.glob('*') if f.is_file()
        ) / (1024**2)
        print(f"\n   Общий размер кэша: {cache_size:.1f} MB")

        print("\n✅ Теперь можно запустить поиск:")
        print("   python step2_search.py")
        print("   или")
        print("   streamlit run app.py")

    except FileNotFoundError as e:
        print(f"\n❌ Ошибка: Файл не найден")
        print(f"   {e}")
        print("\nПроверьте, что файлы данных находятся в:")
        print(f"   {config.DATA_DIR}")

    except Exception as e:
        print(f"\n❌ Произошла ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
