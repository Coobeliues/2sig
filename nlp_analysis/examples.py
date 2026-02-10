"""
Примеры использования всех модулей проекта
"""

import pandas as pd
from semantic_search import SemanticSearch
from advanced_analytics import (
    SpamDetector,
    AspectExtractor,
    DishExtractor,
    TrendAnalyzer
)
from barber_tracker import SpecialistTracker


def example_1_basic_search():
    """
    Пример 1: Базовый семантический поиск
    """
    print("=" * 80)
    print("ПРИМЕР 1: Базовый семантический поиск")
    print("=" * 80)

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

    # Тестовые запросы
    queries = [
        "уютное кафе с вкусным кофе",
        "недорогой ресторан с большими порциями",
        "тихое место для работы с wi-fi",
        "романтический ресторан для свидания",
    ]

    for query in queries:
        print(f"\n🔍 Запрос: '{query}'")
        results = search_engine.search_places(query, top_k=5)

        for idx, row in results.iterrows():
            print(f"{idx + 1}. {row['name']} - {row['rating']:.1f}⭐ "
                  f"(релевантность: {row['final_score']:.3f})")

            # Показываем один релевантный отзыв
            highlights = search_engine.get_place_highlights(
                row['place_id'], query, top_k=1
            )
            if highlights:
                print(f"   💬 \"{highlights[0][:100]}...\"")
        print()


def example_2_spam_detection():
    """
    Пример 2: Детекция спама и фейковых отзывов
    """
    print("=" * 80)
    print("ПРИМЕР 2: Детекция спама и накрутки")
    print("=" * 80)

    # Загрузка данных
    reviews = pd.read_csv('reviews_full.csv')
    spam_detector = SpamDetector()

    # Анализ случайных отзывов
    print("\n🔍 Анализ случайных отзывов:\n")
    for i in range(5):
        review = reviews.iloc[i].to_dict()
        metrics = spam_detector.analyze_review(review)

        print(f"Отзыв {i + 1}:")
        print(f"  Текст: {review['review_text'][:80]}...")
        print(f"  Spam Score: {metrics['spam_score']:.2f}")
        print(f"  Подозрительный: {'Да ⚠️' if metrics['is_suspicious'] else 'Нет ✅'}")
        print()

    # Анализ заведения на накрутку
    print("\n🏢 Анализ заведений на накрутку:\n")

    for place_id in reviews['place_id'].unique()[:5]:
        place_reviews = reviews[reviews['place_id'] == place_id]

        if len(place_reviews) >= 5:
            manipulation = spam_detector.detect_place_manipulation(place_reviews)
            place_name = place_reviews.iloc[0].get('place_name', f'Place {place_id}')

            print(f"{place_name}:")
            print(f"  Manipulation Score: {manipulation['manipulation_score']:.2f}")
            print(f"  5-звездочных отзывов: {manipulation['five_star_ratio']:.1%}")
            print(f"  Накрутка: {'Да ⚠️' if manipulation.get('is_manipulated') else 'Нет ✅'}")
            print()


def example_3_aspect_analysis():
    """
    Пример 3: Анализ аспектов (ABSA)
    """
    print("=" * 80)
    print("ПРИМЕР 3: Анализ аспектов (ABSA)")
    print("=" * 80)

    reviews = pd.read_csv('reviews_full.csv')
    aspect_extractor = AspectExtractor()

    # Анализ отдельного отзыва
    sample_review = reviews.iloc[10]['review_text']
    print(f"\n📝 Отзыв: {sample_review}\n")

    aspects = aspect_extractor.analyze_review(sample_review)
    print("Найденные аспекты:")
    for aspect, data in aspects.items():
        emoji = "😊" if data['sentiment'] > 0 else ("😠" if data['sentiment'] < 0 else "😐")
        print(f"  {aspect}: {data['label']} {emoji} (score: {data['sentiment']:.2f})")

    # Агрегированный анализ заведения
    print("\n\n🏢 Агрегированный анализ заведения:\n")

    place_id = reviews.iloc[0]['place_id']
    place_reviews = reviews[reviews['place_id'] == place_id]
    place_aspects = aspect_extractor.aggregate_place_aspects(place_reviews)

    for aspect, data in sorted(
        place_aspects.items(),
        key=lambda x: x[1]['mention_count'],
        reverse=True
    ):
        if data['mention_count'] >= 2:
            print(f"{aspect}:")
            print(f"  Средняя тональность: {data['avg_sentiment']:.2f}")
            print(f"  Упоминаний: {data['mention_count']}")
            print(f"  Позитивных: {data['positive_ratio']:.1%}")
            print()


def example_4_dish_extraction():
    """
    Пример 4: Извлечение названий блюд
    """
    print("=" * 80)
    print("ПРИМЕР 4: Извлечение названий блюд")
    print("=" * 80)

    reviews = pd.read_csv('reviews_full.csv')
    dish_extractor = DishExtractor()

    # Поиск популярных блюд
    print("\n🍽️ Топ-20 популярных блюд/напитков:\n")

    popular_dishes = dish_extractor.get_popular_dishes(reviews, top_k=20)

    for i, (dish, count) in enumerate(popular_dishes, 1):
        print(f"{i:2}. {dish:20} - {count} упоминаний")


def example_5_trend_analysis():
    """
    Пример 5: Анализ трендов
    """
    print("=" * 80)
    print("ПРИМЕР 5: Анализ трендов")
    print("=" * 80)

    reviews = pd.read_csv('reviews_full.csv')
    places = pd.read_csv('places.csv')
    trend_analyzer = TrendAnalyzer()

    # Добавляем названия к отзывам
    reviews = reviews.merge(
        places[['id', 'name']],
        left_on='place_id',
        right_on='id',
        how='left'
    )

    print("\n📈 Анализ трендов заведений:\n")

    # Анализируем несколько заведений
    for place_id in reviews['place_id'].unique()[:5]:
        place_reviews = reviews[reviews['place_id'] == place_id]

        if len(place_reviews) >= 10:
            trend = trend_analyzer.analyze_rating_trend(place_reviews)
            place_name = place_reviews.iloc[0]['name']

            print(f"{place_name}:")
            print(f"  Тренд: {trend.get('description', 'Недостаточно данных')}")
            if 'delta' in trend:
                print(f"  Изменение: {trend['delta']:+.2f}")
                print(f"  Текущий средний рейтинг: {trend['current_avg']:.2f}")
            print()

    # Сезонные паттерны
    if 'date' in reviews.columns:
        print("\n🌍 Сезонные паттерны (все заведения):\n")
        seasonal = trend_analyzer.detect_seasonal_patterns(reviews)

        if seasonal:
            print(f"Лучший месяц: {seasonal.get('best_month', 'N/A')}")
            print(f"Худший месяц: {seasonal.get('worst_month', 'N/A')}")


def example_6_specialist_tracking():
    """
    Пример 6: Трекинг специалистов
    """
    print("=" * 80)
    print("ПРИМЕР 6: Трекинг специалистов (барберы, официанты)")
    print("=" * 80)

    reviews = pd.read_csv('reviews_full.csv')
    places = pd.read_csv('places.csv')

    # Добавляем информацию о заведениях
    reviews = reviews.merge(
        places[['id', 'name', 'category']],
        left_on='place_id',
        right_on='id',
        how='left'
    )
    reviews.rename(columns={'name': 'place_name'}, inplace=True)

    tracker = SpecialistTracker()

    # Построение базы данных специалистов
    print("\n👥 Построение базы данных специалистов...\n")
    specialist_db = tracker.build_specialist_database(reviews)

    print(f"Найдено {len(specialist_db)} специалистов\n")
    print("Топ-10 специалистов по упоминаниям:\n")
    print(specialist_db.head(10)[['name', 'type', 'mentions', 'places_count']])

    # Поиск конкретного специалиста
    if len(specialist_db) > 0:
        # Берем первого специалиста для примера
        example_name = specialist_db.iloc[0]['name'].split()[0]  # Берем только имя

        print(f"\n\n🔍 Поиск специалиста '{example_name}':\n")
        results = tracker.find_specialist(example_name, specialist_db, threshold=0.6)

        for result in results[:3]:
            print(f"{result['name']} ({result['type']})")
            print(f"  Схожесть: {result['similarity']:.2f}")
            print(f"  Места работы: {', '.join(result['current_places'][:2])}")
            print(f"  Упоминаний: {result['mentions']}")
            print()


def example_7_combined_search():
    """
    Пример 7: Комбинированный поиск с фильтрами
    """
    print("=" * 80)
    print("ПРИМЕР 7: Комбинированный поиск с фильтрами")
    print("=" * 80)

    # Инициализация
    search_engine = SemanticSearch()
    search_engine.load_data('reviews_full.csv', 'places.csv')
    search_engine.create_embeddings(cache_path='cache/embeddings.pkl')
    search_engine.build_index()

    spam_detector = SpamDetector()
    aspect_extractor = AspectExtractor()

    # Поиск с последующим анализом
    query = "кафе с хорошим обслуживанием"
    print(f"\n🔍 Запрос: '{query}'\n")

    results = search_engine.search_places(query, top_k=10)

    for idx, row in results.iterrows():
        print(f"\n{idx + 1}. {row['name']} ⭐ {row['rating']:.1f}")
        print(f"   📍 {row['address']}")

        # Анализ аспектов для заведения
        place_reviews = search_engine.reviews_df[
            search_engine.reviews_df['place_id'] == row['place_id']
        ]

        # Проверка на спам
        manipulation = spam_detector.detect_place_manipulation(place_reviews)
        if manipulation.get('is_manipulated'):
            print("   ⚠️ Возможная накрутка отзывов!")

        # Аспекты
        aspects = aspect_extractor.aggregate_place_aspects(place_reviews)
        if 'сервис' in aspects:
            service_data = aspects['сервис']
            print(f"   👔 Сервис: {service_data['avg_sentiment']:.2f} "
                  f"({service_data['mention_count']} упоминаний)")


def main():
    """
    Запуск всех примеров
    """
    examples = [
        ("Базовый поиск", example_1_basic_search),
        ("Детекция спама", example_2_spam_detection),
        ("Анализ аспектов", example_3_aspect_analysis),
        ("Извлечение блюд", example_4_dish_extraction),
        ("Анализ трендов", example_5_trend_analysis),
        ("Трекинг специалистов", example_6_specialist_tracking),
        ("Комбинированный поиск", example_7_combined_search),
    ]

    print("\n" + "=" * 80)
    print("ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ ПРОЕКТА")
    print("=" * 80)
    print("\nДоступные примеры:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"{i}. {name}")

    print("\n0. Запустить все примеры")
    print("=" * 80)

    choice = input("\nВыберите пример (0-7): ").strip()

    if choice == "0":
        for name, func in examples:
            try:
                func()
                input("\nНажмите Enter для следующего примера...")
            except Exception as e:
                print(f"❌ Ошибка в примере '{name}': {e}")
                import traceback
                traceback.print_exc()
    elif choice.isdigit() and 1 <= int(choice) <= len(examples):
        name, func = examples[int(choice) - 1]
        try:
            func()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("Неверный выбор!")


if __name__ == "__main__":
    main()
