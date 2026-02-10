"""
Семантический поиск заведений по описательным запросам
"""

import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
from typing import List, Tuple
import pickle
from pathlib import Path


class SemanticSearch:
    """
    Класс для семантического поиска заведений по отзывам
    """

    def __init__(self, model_name: str = 'sentence-transformers/LaBSE'):
        """
        Args:
            model_name: Название модели для создания эмбеддингов
                Рекомендуемые модели:
                - 'sentence-transformers/LaBSE' (109 языков, включая русский и казахский)
                - 'DeepPavlov/rubert-base-cased-sentence' (только русский, быстрее)
                - 'ai-forever/sbert_large_nlu_ru' (русский, высокое качество)
        """
        print(f"Загрузка модели {model_name}...")
        self.model = SentenceTransformer(model_name)
        self.index = None
        self.reviews_df = None
        self.places_df = None

    def load_data(self, reviews_path: str, places_path: str):
        """Загрузка данных отзывов и заведений"""
        print("Загрузка данных...")
        self.reviews_df = pd.read_csv(reviews_path)
        self.places_df = pd.read_csv(places_path)

        # Базовая очистка
        self.reviews_df['review_text'] = self.reviews_df['review_text'].fillna('')
        self.reviews_df = self.reviews_df[self.reviews_df['review_text'].str.len() > 10]

        print(f"Загружено {len(self.reviews_df)} отзывов и {len(self.places_df)} заведений")

    def create_embeddings(self, batch_size: int = 32, cache_path: str = None):
        """
        Создание эмбеддингов для всех отзывов

        Args:
            batch_size: Размер батча для обработки
            cache_path: Путь для кэширования эмбеддингов
        """
        if cache_path and Path(cache_path).exists():
            print(f"Загрузка эмбеддингов из кэша {cache_path}...")
            with open(cache_path, 'rb') as f:
                self.embeddings = pickle.load(f)
            print(f"Загружено {len(self.embeddings)} эмбеддингов из кэша")
            return

        print("Создание эмбеддингов...")
        reviews_text = self.reviews_df['review_text'].tolist()

        # Создание эмбеддингов батчами для экономии памяти
        self.embeddings = self.model.encode(
            reviews_text,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True
        )

        # Кэширование
        if cache_path:
            print(f"Сохранение эмбеддингов в {cache_path}...")
            Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, 'wb') as f:
                pickle.dump(self.embeddings, f)

        print(f"Создано {len(self.embeddings)} эмбеддингов размерности {self.embeddings.shape[1]}")

    def build_index(self, use_gpu: bool = False):
        """
        Построение FAISS индекса для быстрого поиска

        Args:
            use_gpu: Использовать GPU для ускорения (требуется faiss-gpu)
        """
        print("Построение FAISS индекса...")
        dimension = self.embeddings.shape[1]

        # Для небольших датасетов используем простой индекс
        if len(self.embeddings) < 100000:
            self.index = faiss.IndexFlatIP(dimension)  # Inner Product (косинусное сходство)
        else:
            # Для больших датасетов используем индекс с квантизацией
            nlist = 100  # количество кластеров
            quantizer = faiss.IndexFlatIP(dimension)
            self.index = faiss.IndexIVFFlat(quantizer, dimension, nlist)
            self.index.train(self.embeddings)

        # Нормализуем эмбеддинги для косинусного сходства
        faiss.normalize_L2(self.embeddings)
        self.index.add(self.embeddings)

        if use_gpu and faiss.get_num_gpus() > 0:
            print("Перенос индекса на GPU...")
            res = faiss.StandardGpuResources()
            self.index = faiss.index_cpu_to_gpu(res, 0, self.index)

        print(f"Индекс построен: {self.index.ntotal} векторов")

    def search_reviews(self, query: str, top_k: int = 20) -> pd.DataFrame:
        """
        Поиск релевантных отзывов по запросу

        Args:
            query: Текстовый запрос пользователя
            top_k: Количество результатов

        Returns:
            DataFrame с релевантными отзывами
        """
        # Создаем эмбеддинг запроса
        query_embedding = self.model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(query_embedding)

        # Поиск ближайших векторов
        distances, indices = self.index.search(query_embedding, top_k)

        # Получаем релевантные отзывы
        results = self.reviews_df.iloc[indices[0]].copy()
        results['similarity_score'] = distances[0]

        return results

    def search_places(self, query: str, top_k: int = 10,
                     min_reviews: int = 3, aggregation: str = 'mean') -> pd.DataFrame:
        """
        Поиск заведений по описательному запросу

        Args:
            query: Запрос пользователя (например, "уютное кафе с вкусным кофе")
            top_k: Количество заведений в результате
            min_reviews: Минимальное количество релевантных отзывов для заведения
            aggregation: Метод агрегации ('mean', 'max', 'weighted')

        Returns:
            DataFrame с топ заведениями
        """
        # Находим релевантные отзывы
        relevant_reviews = self.search_reviews(query, top_k=200)

        # Группируем по заведениям
        place_scores = relevant_reviews.groupby('place_id').agg({
            'similarity_score': ['mean', 'max', 'count']
        }).reset_index()

        place_scores.columns = ['place_id', 'avg_score', 'max_score', 'review_count']

        # Фильтруем по минимальному количеству отзывов
        place_scores = place_scores[place_scores['review_count'] >= min_reviews]

        # Выбираем метод агрегации
        if aggregation == 'mean':
            place_scores['final_score'] = place_scores['avg_score']
        elif aggregation == 'max':
            place_scores['final_score'] = place_scores['max_score']
        elif aggregation == 'weighted':
            # Взвешенная оценка: учитываем количество релевантных отзывов
            place_scores['final_score'] = (
                place_scores['avg_score'] * np.log1p(place_scores['review_count'])
            )

        # Сортируем и берем топ
        place_scores = place_scores.nlargest(top_k, 'final_score')

        # Добавляем информацию о заведениях
        results = place_scores.merge(
            self.places_df,
            left_on='place_id',
            right_on='id',
            how='left'
        )

        return results[['name', 'address', 'category', 'rating',
                       'final_score', 'review_count', 'place_id']]

    def get_place_highlights(self, place_id: int, query: str, top_k: int = 3) -> List[str]:
        """
        Получить самые релевантные отзывы для заведения по запросу

        Args:
            place_id: ID заведения
            query: Запрос пользователя
            top_k: Количество отзывов

        Returns:
            Список текстов отзывов
        """
        relevant_reviews = self.search_reviews(query, top_k=100)
        place_reviews = relevant_reviews[relevant_reviews['place_id'] == place_id]

        return place_reviews.nlargest(top_k, 'similarity_score')['review_text'].tolist()


def main():
    """Пример использования"""

    # Инициализация
    search_engine = SemanticSearch(model_name='sentence-transformers/LaBSE')

    # Загрузка данных
    search_engine.load_data(
        reviews_path='reviews_full.csv',
        places_path='places.csv'
    )

    # Создание эмбеддингов (с кэшированием)
    search_engine.create_embeddings(
        batch_size=32,
        cache_path='cache/embeddings.pkl'
    )

    # Построение индекса
    search_engine.build_index()

    # Пример поиска
    query = "уютное кафе с вкусным кофе"
    results = search_engine.search_places(query, top_k=10)

    print(f"\n🔍 Результаты поиска по запросу: '{query}'\n")
    print(results.to_string(index=False))

    # Показываем релевантные отзывы для топ заведения
    if len(results) > 0:
        top_place_id = results.iloc[0]['place_id']
        top_place_name = results.iloc[0]['name']
        highlights = search_engine.get_place_highlights(top_place_id, query, top_k=3)

        print(f"\n💬 Релевантные отзывы для '{top_place_name}':\n")
        for i, review in enumerate(highlights, 1):
            print(f"{i}. {review[:200]}...")


if __name__ == "__main__":
    main()
