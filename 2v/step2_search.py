

import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import pickle
from typing import List, Tuple, Optional
import time
import os
import torch
import unicodedata
from transformers import pipeline

import config


class SemanticSearch:

    def __init__(self):
        print("=" * 80)
        print("ИНИЦИАЛИЗАЦИЯ ПОИСКА")
        print("=" * 80)

        # Проверка наличия кэша
        if not config.EMBEDDINGS_CACHE.exists():
            raise FileNotFoundError(
                f"Кэш не найден: {config.EMBEDDINGS_CACHE}\n"
                f"   Сначала запустите: python step1_prepare.py"
            )

        if not config.INDEX_CACHE.exists():
            raise FileNotFoundError(
                f"Индекс не найден: {config.INDEX_CACHE}\n"
                f"   Сначала запстите: python step1_prepare.py"
            )

        if not config.METADATA_CACHE.exists():
            raise FileNotFoundError(
                f"Метаданные не найдены: {config.METADATA_CACHE}\n"
                f"   Сначала запустите: python step1_prepare.py"
            )

        if hasattr(config, "GPU_ID"):
            os.environ["CUDA_VISIBLE_DEVICES"] = str(config.GPU_ID)

        # Загрузка sentiment модели
        print("\nЗагрузка sentiment модели...")
        self.sentiment_model = pipeline(
            "sentiment-analysis",
            model="blanchefort/rubert-base-cased-sentiment",
            device=0 if torch.cuda.is_available() else -1
        )
        print("Sentiment модель загружена")

        # Загрузка модели эмбеддингов
        print(f"\nЗагрузка модели: {config.MODEL_NAME}")
        start = time.time()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Используем устройство: {device}")

        self.model = SentenceTransformer(config.MODEL_NAME, device=device)


        if device == "cuda" and getattr(config, "USE_FP16", True):
            self.model = self.model.half()
            print("FP16 включён")

        print(f"Модель загружена за {time.time() - start:.1f} сек")


        # Загрузка индекса
        print(f"\nЗагрузка FAISS индекса...")
        start = time.time()
        self.index = faiss.read_index(str(config.INDEX_CACHE))
        print(f"Индекс загружен за {time.time() - start:.1f} сек")
        print(f"   Векторов в индексе: {self.index.ntotal:,}")

        # Загрузка метаданных
        print(f"\nЗагрузка метаданных...")
        with open(config.METADATA_CACHE, 'rb') as f:
            metadata = pickle.load(f)

        self.reviews_df = metadata['reviews']
        self.places_df = metadata['places']
        self.text_column = metadata['text_column']

        # Убираем отывы без place_firm_id
        initial_count = len(self.reviews_df)
        self.reviews_df = self.reviews_df[
            self.reviews_df['place_firm_id'].notna()
        ].copy()
        removed = initial_count - len(self.reviews_df)
        if removed > 0:
            print(f"   Удалено {removed} отзывов без place_firm_id")

        print(f"Загружено:")
        print(f"   Отзывов: {len(self.reviews_df):,}")
        print(f"   Заведений: {len(self.places_df):,}")
  
        # Кэш для последних результатов
        self._last_relevant_reviews = None 
        self._last_query_sentiment = None

        print("\n" + "=" * 80)
        print("ПОИСК ГОТОВ К РАБОТЕ")
        print("=" * 80)

    def _get_query_sentiment(self, query: str) -> str:
        """Получить sentiment запроса"""
        result = self.sentiment_model(query[:512])[0]  # Ограничиваем длину
        return result['label'].lower()

    def search_reviews(self, query: str, top_k: int = 200) -> pd.DataFrame:
        """Поиск релевантных отзывов по запрсу. Возвращает DataFrame с отзывами и scores."""
        query = normalize_text(query)

        if len(query) == 0:
            raise ValueError("Пустой или некорректный запрос")

        # Определяем sentiment запроса
        query_sentiment = self._get_query_sentiment(query)
        self._last_query_sentiment = query_sentiment

        # Создаём эмбеддинг запроса
        query_embedding = self.model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=False
        )

        if query_embedding.dtype != np.float32:
            query_embedding = query_embedding.astype(np.float32)

        faiss.normalize_L2(query_embedding)

        # Берём больше кандидатов для последующей фильтрации
        search_k = min(top_k * 5, self.index.ntotal)
        distances, indices = self.index.search(query_embedding, search_k)

        # Фильтруем невалидные индексы
        valid_mask = indices[0] < len(self.reviews_df)
        valid_indices = indices[0][valid_mask]
        valid_distances = distances[0][valid_mask]

        if len(valid_indices) == 0:

            return pd.DataFrame()

        results = self.reviews_df.iloc[valid_indices].copy()
        results['similarity_score'] = valid_distances

        # Дополнительная проверка place_firm_id после фильтрации
        results = results[results['place_firm_id'].notna()].copy()

        if results.empty:

            return results

        # Sentiment Analysis для отзывов
        texts = results[self.text_column].fillna("").astype(str).tolist()
        # Ограничиваем длину текстов для модели
        texts = [t[:512] for t in texts]

        sentiments = self.sentiment_model(texts, batch_size=32, truncation=True)
        results['sentiment_label'] = [s['label'].lower() for s in sentiments]
        results['sentiment_score'] = [s['score'] for s in sentiments]

        # Базовый вес sentiment
        results['sentiment_weight'] = results['sentiment_label'].apply(sentiment_to_weight)

        # Sentiment alignment: бустим совпадающий sentiment, штрафуем противоположный
        def align_sentiment(row):
            review_sent = row['sentiment_label']

            if query_sentiment == "negative":
                if review_sent == "positive":
                    return 0.05  # Почти убваем позитивные отзывы
                elif review_sent == "negative":
                    return 2.5   # Сильно бустим негативные
                else:  # neutral
                    return 0.5

            elif query_sentiment == "positive":
                if review_sent == "negative":
                    return 0.05  # Почти убиваем негативные
                elif review_sent == "positive":
                    return 2.0   # Бустим позитвные
                else:  # neutral
                    return 0.7

            else:  # neutral query
                return 1.0

        results['sentiment_alignment'] = results.apply(align_sentiment, axis=1)

        # Финальный score
        results['final_review_score'] = (
            results['similarity_score']
            * results['sentiment_weight']
            * results['sentiment_alignment']
        )

        # Фильтруем по минимальному порогу
        min_score = 0.15 if query_sentiment == "negative" else 0.20
        results = results[results['final_review_score'] > min_score]

        if results.empty:

            return results


        # Возвращаем top_k лучших
        return results.nlargest(top_k, 'final_review_score')

    def search_places(
        self,
        query: str,
        top_k: int = None,
        min_reviews: int = None,
        aggregation: str = None
    ) -> pd.DataFrame:
        """Поиск заведений по описательному запросу. Возвращает DataFrame с топ заведениями."""
        # Defaults
        top_k = top_k or config.DEFAULT_TOP_K
        min_reviews = min_reviews or config.DEFAULT_MIN_REVIEWS
        aggregation = aggregation or config.DEFAULT_AGGREGATION

        # 1. Находим релевантные отзывы
        relevant_reviews = self.search_reviews(query, top_k=300)

        if relevant_reviews.empty:
            print("Не найдено релевантных отзывов")
            return pd.DataFrame()

        # Конвертируем place_firm_id в int для корректной группировки
        relevant_reviews['place_firm_id'] = relevant_reviews['place_firm_id'].astype(int)

        # Берём только топ отзывов на заведение
        relevant_reviews = (
            relevant_reviews
            .sort_values("final_review_score", ascending=False)
            .groupby("place_firm_id")
            .head(15)  # Максимум 15 отзвов на заведение
        )

        self._last_relevant_reviews = relevant_reviews.copy()

        query_sentiment = self._last_query_sentiment or "neutral"

        # 2. Агрегация по заведениям
        place_scores = relevant_reviews.groupby('place_firm_id').agg({
            'final_review_score': ['mean', 'max', 'count', 'sum'],
            'sentiment_label': [
                lambda x: (x == 'positive').sum(),
                lambda x: (x == 'negative').sum(),
                lambda x: (x == 'neutral').sum()
            ]
        }).reset_index()

        place_scores.columns = [
            'place_firm_id',
            'avg_score', 'max_score', 'review_count', 'total_score',
            'positive_reviews', 'negative_reviews', 'neutral_reviews'
        ]

        # 3. Фильтруем по минимальному количеству отзывов
        place_scores = place_scores[place_scores['review_count'] >= min_reviews]

        if len(place_scores) == 0:
            print(f"Не найдено заведений с минимум {min_reviews} релевантными отзывами")

            return pd.DataFrame()

        # 4. Вычисляем финальный score
        if aggregation == 'mean':
            place_scores['final_score'] = place_scores['avg_score']

        elif aggregation == 'max':
            place_scores['final_score'] = place_scores['max_score']

        elif aggregation == 'weighted':
            # Учитываем sentiment соотношение при weighted-агрегации
            if query_sentiment == 'negative':
                # Для негативных запросов: больше негативных отзывов = лучше
                sentiment_ratio = (
                    (place_scores['negative_reviews'] + 1) /
                    (place_scores['positive_reviews'] + place_scores['neutral_reviews'] + 1)
                )
            else:
                # Для позитивных/нейтральных: больше позиивных = лучше
                sentiment_ratio = (
                    (place_scores['positive_reviews'] + 1) /
                    (place_scores['negative_reviews'] + 1)
                )

            place_scores['final_score'] = (
                place_scores['avg_score']
                * np.log1p(place_scores['review_count'])
                * np.sqrt(sentiment_ratio)
            )
        else:
            raise ValueError(f"Unknown aggregation method: {aggregation}")

        # 5. Сортируем и берём топ
        place_scores = place_scores.nlargest(top_k * 2, 'final_score')  # Берём с запасом

        # 6. Добавляем информацию о заведениях
        # Приводим firm_id к int для корректного merge
        places_df = self.places_df.copy()
        if 'firm_id' in places_df.columns:
            places_df['firm_id'] = places_df['firm_id'].astype(int)

        results = place_scores.merge(
            places_df,
            left_on='place_firm_id',
            right_on='firm_id',
            how='left'
        )

        # Дедупликация по имени
        if 'name' in results.columns:
            results = results.drop_duplicates(subset=['name'], keep='first')

        # Отсекаем записи с пустыми именами
        if 'name' in results.columns:
            results = results[results['name'].notna() & (results['name'] != 'nan')]

        # Берём финальный top_k
        results = results.head(top_k)

        # 7. Выбираем нужные колонки
        columns = [
            'name', 'address', 'category', 'rating',
            'final_score', 'avg_score', 'review_count',
            'positive_reviews', 'negative_reviews', 'neutral_reviews',
            'place_firm_id'
        ]
        available_columns = [col for col in columns if col in results.columns]


        return results[available_columns].reset_index(drop=True)

    def get_place_highlights(
        self,
        place_firm_id: int,
        query: str = None,
        top_k: int = 3
    ) -> List[str]:
        """Получить самые релевантные отзывы для заведения из последнего поиска."""
        if self._last_relevant_reviews is None or self._last_relevant_reviews.empty:
            return []

        # Фильтруем по заведению
        place_reviews = self._last_relevant_reviews[
            self._last_relevant_reviews['place_firm_id'] == int(place_firm_id)
        ]

        if len(place_reviews) == 0:

            return []

        # Берём топ по финальному score
        top_reviews = place_reviews.nlargest(top_k, 'final_review_score')

        # Форматируем тексты
        highlights = []
        for _, row in top_reviews.iterrows():
            text = row.get(self.text_column, "")
            if isinstance(text, str) and len(text.strip()) > 20:
                text = normalize_text(text)
                sentiment = row.get('sentiment_label', 'neutral')
                indicator = {'positive': '[+]', 'negative': '[-]', 'neutral': '[~]'}.get(sentiment, '')
                highlights.append(f"{indicator} {text}")

        return highlights

    def get_place_sentiment_stats(self, place_firm_id: int) -> dict:
        """Получить статистику sentiment для заведения"""
        if self._last_relevant_reviews is None:

            return {'positive': 0, 'negative': 0, 'neutral': 0}

        place_reviews = self._last_relevant_reviews[
            self._last_relevant_reviews['place_firm_id'] == int(place_firm_id)
        ]

        if place_reviews.empty:

            return {'positive': 0, 'negative': 0, 'neutral': 0}

        return {
            'positive': (place_reviews['sentiment_label'] == 'positive').sum(),
            'negative': (place_reviews['sentiment_label'] == 'negative').sum(),
            'neutral': (place_reviews['sentiment_label'] == 'neutral').sum()
        }


def sentiment_to_weight(label: str) -> float:
    """Преобразуем sentiment в числовой вес"""
    label = label.lower() if isinstance(label, str) else "neutral"
    weights = {
        "positive": 1.2,
        "neutral": 1.0,
        "negative": 0.8  # Базовый вес, alignment сделает основную работу
    }


    return weights.get(label, 1.0)


def normalize_text(text: str) -> str:
    """Нормализация текста"""
    if not isinstance(text, str):
        return ""

    # Unicode normalize
    text = unicodedata.normalize("NFKC", text)

    # Убираем битые символы
    text = text.encode("utf-8", "ignore").decode("utf-8", "ignore")

    # Убираем лишние пробелы
    text = " ".join(text.split())


    return text


def interactive_search():
    print("\n" + "=" * 80)
    print("ИНТЕРАКТИВНЫЙ ПОИСК ЗАВЕДЕНИЙ")
    print("=" * 80)


    try:
        search = SemanticSearch()

        print("\nПримеры запросов:")
        print("   Позитивные: уютное кафе с вкусным кофе")
        print("   Негативные: ужасный сервис, невкусная еда")
        print("   Нейтральные: кафе с Wi-Fi для работы")
        print("\n   (Введите 'exit' для выхода)")
        print("=" * 80)

        while True:
            print("\n" + "-" * 80)
            query = input("Запрос: ").strip()

            if not query:
                continue

            if query.lower() in ['exit', 'quit', 'выход', 'q']:
                print("\nДо свидания!")
                break

            print(f"\nПоиск по запросу: '{query}'...\n")
            start = time.time()

            results = search.search_places(query, top_k=10)
            elapsed = time.time() - start

            # Показываем sentiment запроса
            query_sentiment = search._last_query_sentiment or "neutral"
            sentiment_tag = {'positive': '[POS]', 'negative': '[NEG]', 'neutral': '[NEU]'}.get(query_sentiment, '[?]')
            print(f"   Sentiment запроса: {sentiment_tag} {query_sentiment.upper()}")

            if len(results) == 0:
                print("\nНичего не найдено")
                print("   Попробуйте изменить запрос")
                continue
 
            print(f"\nНайдено {len(results)} заведений за {elapsed*1000:.0f}ms\n")  
            print("=" * 80)

 
            for idx, row in results.iterrows():
                name = row.get('name', 'N/A')
                print(f"\n{idx + 1}. {name}")

                address = row.get('address', 'N/A')
                if pd.notna(address) and address != 'N/A':
                    print(f"   Адрес: {address}")

                category = row.get('category', '')
                if pd.notna(category) and category:
                    print(f"   Категория: {category}")

                rating = row.get('rating')
                if pd.notna(rating):
                    print(f"   Рейтинг: {rating:.1f}")

                print(f"   Релевантность: {row['final_score']:.3f}")
                print(f"   Релевантных отзывов: {int(row['review_count'])}")

                # Статистика sentiment
                pos = int(row.get('positive_reviews', 0))
                neg = int(row.get('negative_reviews', 0))
                neu = int(row.get('neutral_reviews', 0))
                print(f"   Sentiment: +{pos} ~{neu} -{neg}")

                # Показываем релевантные отзывы
                place_id = row.get('place_firm_id')
                if pd.notna(place_id):
                    highlights = search.get_place_highlights(int(place_id), top_k=2)
                    for h in highlights:
                        # Обрезаем длинные отзывы
                        if len(h) > 200:
                            h = h[:200] + "..."
                        print(f"   > {h}")

            print("\n" + "=" * 80)
 
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
    except Exception as e:
        print(f"\nОшибка: {e}")
        import traceback
        traceback.print_exc()


def demo_search():
    print("\n" + "=" * 80)
    print("ДЕМО: Автоматический поиск")
    print("=" * 80)

    try:
        search = SemanticSearch()

        demo_queries = [
            ("уютное кафе с вкусным кофе", "positive"),
            ("ужасный сервис, невкусная еда", "negative"),
            ("тихое место для работы", "neutral"),
        ]

        for query, expected_sentiment in demo_queries:
            print(f"\n{'='*80}")
            print(f"Запрос: '{query}'")
            print(f"   Ожидаемый sentiment: {expected_sentiment}")
            print("=" * 80)

            start = time.time()
            results = search.search_places(query, top_k=5)
            elapsed = time.time() - start

            actual_sentiment = search._last_query_sentiment
            print(f"\n   Фактический sentiment: {actual_sentiment}")
            print(f"Поиск выполнен за {elapsed*1000:.0f}ms")
            print(f"Найдено {len(results)} заведений:\n")

            for idx, row in results.iterrows():
                name = row.get('name', 'N/A')
                rating = row.get('rating', 0)
                pos = int(row.get('positive_reviews', 0))
                neg = int(row.get('negative_reviews', 0))

                print(f"{idx + 1}. {name} - рейтинг {rating:.1f}")
                print(f"   Score: {row['final_score']:.3f} | "
                      f"Отзывов: {int(row['review_count'])} | "
                      f"+{pos} -{neg}")

            input("\nНажмите Enter для следующего запроса...")


    except Exception as e:
        print(f"\nОшибка: {e}")
        import traceback
        traceback.print_exc()


def main():
    print("\n" + "=" * 80) 
    print("SEMANTIC SEARCH - ПОИСК ЗАВЕДЕНИЙ")
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
        print("\nДо свидания!")


if __name__ == "__main__":
    main()

















 
  