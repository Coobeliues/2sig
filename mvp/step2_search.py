"""
ШАГ 2: Поиск заведений
Загружает подготовленные данные и выполняет семантический поиск
"""

import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import pickle
from typing import List, Tuple
import time

import config


class SemanticSearch:
    """Класс для семантического поиска заведений"""

    def __init__(self):
        """Инициализация: загрузка модели и данных из кэша"""
        print("=" * 80)
        print("🔍 ИНИЦИАЛИЗАЦИЯ ПОИСКА")
        print("=" * 80)

        # Проверка наличия кэша
        if not config.EMBEDDINGS_CACHE.exists():
            raise FileNotFoundError(
                f"❌ Кэш не найден: {config.EMBEDDINGS_CACHE}\n"
                f"   Сначала запустите: python step1_prepare.py"
            )

        if not config.INDEX_CACHE.exists():
            raise FileNotFoundError(
                f"❌ Индекс не найден: {config.INDEX_CACHE}\n"
                f"   Сначала запустите: python step1_prepare.py"
            )

        if not config.METADATA_CACHE.exists():
            raise FileNotFoundError(
                f"❌ Метаданные не найдены: {config.METADATA_CACHE}\n"
                f"   Сначала запустите: python step1_prepare.py"
            )

        # Загрузка модели
        print(f"\n⏳ Загрузка модели: {config.MODEL_NAME}")
        start = time.time()
        self.model = SentenceTransformer(config.MODEL_NAME)
        print(f"✅ Модель загружена за {time.time() - start:.1f} сек")

        # Загрузка индекса
        print(f"\n⏳ Загрузка FAISS индекса...")
        start = time.time()
        self.index = faiss.read_index(str(config.INDEX_CACHE))
        print(f"✅ Индекс загружен за {time.time() - start:.1f} сек")
        print(f"   Векторов в индексе: {self.index.ntotal:,}")

        # Загрузка метаданных
        print(f"\n⏳ Загрузка метаданных...")
        with open(config.METADATA_CACHE, 'rb') as f:
            metadata = pickle.load(f)

        self.reviews_df = metadata['reviews']
        self.places_df = metadata['places']
        self.text_column = metadata['text_column']

        print(f"✅ Загружено:")
        print(f"   Отзывов: {len(self.reviews_df):,}")
        print(f"   Заведений: {len(self.places_df):,}")

        print("\n" + "=" * 80)
        print("✅ ПОИСК ГОТОВ К РАБОТЕ")
        print("=" * 80)

    def search_reviews(self, query: str, top_k: int = 200) -> pd.DataFrame:
        """
        Поиск релевантных отзывов по запросу

        Args:
            query: Текстовый запрос пользователя
            top_k: Количество релевантных отзывов

        Returns:
            DataFrame с релевантными отзывами и scores
        """
        # 1. Создаем эмбеддинг запроса
        query_embedding = self.model.encode([query], convert_to_numpy=True)

        # 2. Нормализуем для косинусного сходства
        faiss.normalize_L2(query_embedding)

        # 3. Поиск в FAISS индексе
        distances, indices = self.index.search(query_embedding, top_k)

        # 4. Формируем результаты
        results = self.reviews_df.iloc[indices[0]].copy()
        results['similarity_score'] = distances[0]

        return results

    def search_places(
        self,
        query: str,
        top_k: int = config.DEFAULT_TOP_K,
        min_reviews: int = config.DEFAULT_MIN_REVIEWS,
        aggregation: str = config.DEFAULT_AGGREGATION
    ) -> pd.DataFrame:
        """
        Поиск заведений по описательному запросу

        Args:
            query: Запрос пользователя
            top_k: Количество заведений в результате
            min_reviews: Минимум релевантных отзывов для заведения
            aggregation: Метод агрегации ('mean', 'max', 'weighted')

        Returns:
            DataFrame с топ заведениями
        """
        # 1. Находим релевантные отзывы
        relevant_reviews = self.search_reviews(query, top_k=200)

        # 2. Группируем по заведениям
        place_scores = relevant_reviews.groupby('place_id').agg({
            'similarity_score': ['mean', 'max', 'count']
        }).reset_index()

        place_scores.columns = ['place_id', 'avg_score', 'max_score', 'review_count']

        # 3. Фильтруем по минимальному количеству отзывов
        place_scores = place_scores[place_scores['review_count'] >= min_reviews]

        if len(place_scores) == 0:
            print(f"⚠️  Не найдено заведений с минимум {min_reviews} релевантными отзывами")
            print("   Попробуйте уменьшить min_reviews или изменить запрос")
            return pd.DataFrame()

        # 4. Вычисляем финальный score
        if aggregation == 'mean':
            place_scores['final_score'] = place_scores['avg_score']
        elif aggregation == 'max':
            place_scores['final_score'] = place_scores['max_score']
        elif aggregation == 'weighted':
            # Взвешенный: учитываем и качество и количество
            place_scores['final_score'] = (
                place_scores['avg_score'] * np.log1p(place_scores['review_count'])
            )
        else:
            raise ValueError(f"Unknown aggregation method: {aggregation}")

        # 5. Сортируем и берем топ
        place_scores = place_scores.nlargest(top_k, 'final_score')

        # 6. Добавляем информацию о заведениях
        results = place_scores.merge(
            self.places_df,
            left_on='place_id',
            right_on='id',
            how='left'
        )

        # 7. Выбираем нужные колонки
        columns = ['name', 'address', 'category', 'rating',
                  'final_score', 'avg_score', 'review_count', 'place_id']

        # Проверяем наличие колонок
        available_columns = [col for col in columns if col in results.columns]

        return results[available_columns]

    def get_place_highlights(
        self,
        place_id: int,
        query: str,
        top_k: int = 3
    ) -> List[str]:
        """
        Получить самые релевантные отзывы для заведения

        Args:
            place_id: ID заведения
            query: Запрос пользователя
            top_k: Количество отзывов

        Returns:
            Список текстов отзывов
        """
        # Находим релевантные отзывы
        relevant_reviews = self.search_reviews(query, top_k=100)

        # Фильтруем по заведению
        place_reviews = relevant_reviews[relevant_reviews['place_id'] == place_id]

        if len(place_reviews) == 0:
            return []

        # Берем топ по similarity_score
        top_reviews = place_reviews.nlargest(top_k, 'similarity_score')

        return top_reviews[self.text_column].tolist()


def interactive_search():
    """Интерактивный поиск в терминале"""
    print("\n" + "=" * 80)
    print("🔍 ИНТЕРАКТИВНЫЙ ПОИСК ЗАВЕДЕНИЙ")
    print("=" * 80)

    try:
        # Инициализация
        search = SemanticSearch()

        print("\n💡 Примеры запросов:")
        print("   - уютное кафе с вкусным кофе")
        print("   - недорогой ресторан с большими порциями")
        print("   - тихое место для работы")
        print("   - романтическое место для свидания")
        print("\n   (Введите 'exit' для выхода)")
        print("=" * 80)

        while True:
            # Получение запроса
            print("\n" + "─" * 80)
            query = input("🔍 Ваш запрос: ").strip()

            if not query:
                continue

            if query.lower() in ['exit', 'quit', 'выход']:
                print("\n👋 До свидания!")
                break

            # Поиск
            print(f"\n⏳ Поиск по запросу: '{query}'...\n")
            start = time.time()

            results = search.search_places(query, top_k=10)
            elapsed = time.time() - start

            # Вывод результатов
            if len(results) == 0:
                print("❌ Ничего не найдено")
                print("   Попробуйте изменить запрос")
                continue

            print(f"✅ Найдено {len(results)} заведений за {elapsed*1000:.0f}ms\n")
            print("=" * 80)

            for idx, row in results.iterrows():
                print(f"\n{idx + 1}. {row['name']}")
                print(f"   📍 {row.get('address', 'N/A')}")

                if 'category' in row:
                    print(f"   🏷️  {row['category']}")

                if 'rating' in row and pd.notna(row['rating']):
                    print(f"   ⭐ Рейтинг: {row['rating']:.1f}")

                print(f"   🎯 Релевантность: {row['final_score']:.3f}")
                print(f"   💬 Релевантных отзывов: {int(row['review_count'])}")

                # Показываем один релевантный отзыв
                highlights = search.get_place_highlights(row['place_id'], query, top_k=1)
                if highlights:
                    print(f"   💭 \"{highlights[0][:150]}...\"")

            print("\n" + "=" * 80)

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


def demo_search():
    """Демо поиск с примерами"""
    print("\n" + "=" * 80)
    print("🎮 ДЕМО: Автоматический поиск")
    print("=" * 80)

    try:
        search = SemanticSearch()

        demo_queries = [
            "уютное кафе с вкусным кофе",
            "недорогое место с большими порциями",
            "тихое место для работы",
        ]

        for query in demo_queries:
            print(f"\n{'='*80}")
            print(f"🔍 Запрос: '{query}'")
            print("=" * 80)

            start = time.time()
            results = search.search_places(query, top_k=5)
            elapsed = time.time() - start

            print(f"\n⏱️  Поиск выполнен за {elapsed*1000:.0f}ms")
            print(f"✅ Найдено {len(results)} заведений:\n")

            for idx, row in results.iterrows():
                print(f"{idx + 1}. {row['name']} - ⭐ {row.get('rating', 0):.1f}")
                print(f"   Релевантность: {row['final_score']:.3f} | "
                      f"Отзывов: {int(row['review_count'])}")

            input("\nНажмите Enter для следующего запроса...")

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Главная функция"""
    print("\n" + "=" * 80)
    print("🚀 SEMANTIC SEARCH - ПОИСК ЗАВЕДЕНИЙ")
    print("=" * 80)

    print("\nВыберите режим:")
    print("  1. Интерактивный поиск (вводите свои запросы)")
    print("  2. Демо с примерами")
    print("  3. Выход")

    choice = input("\nВаш выбор (1-3): ").strip()

    if choice == '1':
        interactive_search()
    elif choice == '2':
        demo_search()
    else:
        print("\n👋 До свидания!")


if __name__ == "__main__":
    main()
