"""
Трекинг специалистов (барберов, мастеров) по отзывам
Идея: клиент может найти своего мастера, если тот сменил место работы
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple
import re
from collections import defaultdict
from difflib import SequenceMatcher
import spacy


class SpecialistTracker:
    """
    Отслеживание упоминаний специалистов в отзывах
    """

    def __init__(self):
        try:
            self.nlp = spacy.load("ru_core_news_sm")
        except:
            print("Установите spaCy модель: python -m spacy download ru_core_news_sm")
            self.nlp = None

        # Маркеры упоминания специалистов
        self.specialist_markers = {
            'барбер': ['барбер', 'мастер', 'стригли', 'стрижку делал'],
            'косметолог': ['косметолог', 'мастер', 'процедуру делала'],
            'официант': ['официант', 'официантка', 'обслуживал', 'обслуживала'],
            'повар': ['повар', 'шеф'],
            'бариста': ['бариста', 'кофе делал', 'кофе готовил'],
        }

    def extract_person_names(self, text: str) -> List[str]:
        """
        Извлечение имен из текста с использованием NER

        Returns:
            Список найденных имен
        """
        if not self.nlp:
            # Fallback: простой поиск по паттернам
            return self._extract_names_simple(text)

        doc = self.nlp(text)
        names = []

        for ent in doc.ents:
            if ent.label_ == 'PER':  # PERson
                names.append(ent.text.strip())

        return names

    def _extract_names_simple(self, text: str) -> List[str]:
        """
        Простое извлечение имен без NER
        Ищет слова с заглавной буквы после маркеров
        """
        names = []

        # Паттерн: маркер + имя с заглавной буквы
        patterns = [
            r'(?:мастер|барбер|официант|бариста)\s+([А-ЯЁ][а-яё]+)',
            r'([А-ЯЁ][а-яё]+)\s+(?:отлично|прекрасно|замечательно)',
            r'(?:у|к)\s+([А-ЯЁ][а-яё]+)\s+(?:на|в)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            names.extend(matches)

        return list(set(names))

    def extract_specialist_mentions(self, text: str, category: str = None) -> List[Dict]:
        """
        Извлечение упоминаний специалистов с контекстом

        Args:
            text: Текст отзыва
            category: Категория заведения (для фильтрации типа специалиста)

        Returns:
            Список словарей {name, type, context}
        """
        mentions = []
        sentences = re.split(r'[.!?]', text)

        # Извлекаем имена
        names = self.extract_person_names(text)

        if not names:
            return mentions

        # Определяем тип специалиста и контекст
        for name in names:
            for sentence in sentences:
                if name in sentence:
                    specialist_type = self._identify_specialist_type(sentence, category)
                    mentions.append({
                        'name': name,
                        'type': specialist_type,
                        'context': sentence.strip(),
                        'full_name': self._try_extract_full_name(text, name)
                    })
                    break

        return mentions

    def _identify_specialist_type(self, text: str, category: str = None) -> str:
        """Определение типа специалиста по контексту"""
        text_lower = text.lower()

        # Если известна категория заведения
        if category:
            if 'барбер' in category.lower() or 'парикмахер' in category.lower():
                return 'барбер'
            elif 'кафе' in category.lower() or 'ресторан' in category.lower():
                if any(word in text_lower for word in ['стриг', 'брил', 'машинк']):
                    return 'барбер'
                elif any(word in text_lower for word in ['кофе', 'капучино', 'латте']):
                    return 'бариста'
                else:
                    return 'официант'

        # Определяем по ключевым словам
        for spec_type, markers in self.specialist_markers.items():
            if any(marker in text_lower for marker in markers):
                return spec_type

        return 'специалист'

    def _try_extract_full_name(self, text: str, first_name: str) -> str:
        """Попытка извлечь полное имя (Имя Фамилия)"""
        # Ищем паттерн: Имя + слово с заглавной буквы
        pattern = f'{first_name}\\s+([А-ЯЁ][а-яё]+)'
        match = re.search(pattern, text)

        if match:
            return f"{first_name} {match.group(1)}"
        return first_name

    def build_specialist_database(self, reviews: pd.DataFrame) -> pd.DataFrame:
        """
        Построение базы данных специалистов из отзывов

        Returns:
            DataFrame с колонками: name, type, places, mentions, latest_date
        """
        specialist_data = defaultdict(lambda: {
            'places': set(),
            'place_names': set(),
            'mentions': 0,
            'contexts': [],
            'dates': [],
            'type': 'специалист'
        })

        for _, review in reviews.iterrows():
            mentions = self.extract_specialist_mentions(
                review['review_text'],
                review.get('category', '')
            )

            for mention in mentions:
                name = mention['full_name']
                specialist_data[name]['places'].add(review['place_id'])
                if 'place_name' in review:
                    specialist_data[name]['place_names'].add(review['place_name'])
                specialist_data[name]['mentions'] += 1
                specialist_data[name]['contexts'].append(mention['context'])
                specialist_data[name]['type'] = mention['type']

                if 'date' in review and pd.notna(review['date']):
                    specialist_data[name]['dates'].append(review['date'])

        # Конвертация в DataFrame
        rows = []
        for name, data in specialist_data.items():
            # Фильтруем: минимум 2 упоминания
            if data['mentions'] >= 2:
                rows.append({
                    'name': name,
                    'type': data['type'],
                    'places_count': len(data['places']),
                    'place_ids': list(data['places']),
                    'place_names': list(data['place_names']),
                    'mentions': data['mentions'],
                    'latest_place': list(data['place_names'])[-1] if data['place_names'] else None,
                    'contexts': data['contexts'][:3]  # Первые 3 контекста
                })

        df = pd.DataFrame(rows)
        return df.sort_values('mentions', ascending=False)

    def find_specialist(self, name_query: str, specialist_db: pd.DataFrame,
                       threshold: float = 0.7) -> List[Dict]:
        """
        Поиск специалиста по имени с нечетким совпадением

        Args:
            name_query: Поисковой запрос (имя)
            specialist_db: База данных специалистов
            threshold: Порог схожести (0-1)

        Returns:
            Список найденных специалистов
        """
        results = []

        for _, specialist in specialist_db.iterrows():
            # Нечеткое сравнение имен
            similarity = SequenceMatcher(
                None,
                name_query.lower(),
                specialist['name'].lower()
            ).ratio()

            if similarity >= threshold:
                results.append({
                    'name': specialist['name'],
                    'type': specialist['type'],
                    'similarity': similarity,
                    'current_places': specialist['place_names'],
                    'mentions': specialist['mentions'],
                    'contexts': specialist['contexts']
                })

        return sorted(results, key=lambda x: x['similarity'], reverse=True)

    def track_specialist_movement(self, specialist_name: str,
                                  reviews: pd.DataFrame) -> List[Dict]:
        """
        Отслеживание перемещения специалиста между заведениями

        Args:
            specialist_name: Имя специалиста
            reviews: DataFrame отзывов с датами

        Returns:
            История работы специалиста
        """
        if 'date' not in reviews.columns:
            return []

        # Находим все упоминания
        specialist_reviews = []

        for _, review in reviews.iterrows():
            mentions = self.extract_specialist_mentions(review['review_text'])
            for mention in mentions:
                if specialist_name.lower() in mention['full_name'].lower():
                    specialist_reviews.append({
                        'date': review['date'],
                        'place_id': review['place_id'],
                        'place_name': review.get('place_name', ''),
                        'context': mention['context']
                    })

        # Сортировка по дате
        specialist_reviews = sorted(specialist_reviews, key=lambda x: x['date'])

        # Группировка по заведениям с временными периодами
        workplace_history = []
        current_place = None
        start_date = None

        for review in specialist_reviews:
            if review['place_id'] != current_place:
                if current_place is not None:
                    workplace_history.append({
                        'place_name': prev_place_name,
                        'period': f"{start_date} - {prev_date}"
                    })

                current_place = review['place_id']
                start_date = review['date']
                prev_place_name = review['place_name']

            prev_date = review['date']

        # Добавляем текущее место
        if current_place is not None:
            workplace_history.append({
                'place_name': prev_place_name,
                'period': f"{start_date} - настоящее время"
            })

        return workplace_history


class SpecialistRecommender:
    """
    Рекомендации специалистов на основе отзывов
    """

    def __init__(self, specialist_db: pd.DataFrame, reviews: pd.DataFrame):
        self.specialist_db = specialist_db
        self.reviews = reviews

    def get_top_specialists(self, category: str = None, top_k: int = 10) -> pd.DataFrame:
        """
        Получить топ специалистов по упоминаниям

        Args:
            category: Фильтр по типу специалиста
            top_k: Количество результатов

        Returns:
            DataFrame с топ специалистами
        """
        df = self.specialist_db.copy()

        if category:
            df = df[df['type'] == category]

        return df.nlargest(top_k, 'mentions')

    def find_specialist_by_style(self, description: str) -> List[Dict]:
        """
        Найти специалиста по описанию стиля работы

        Args:
            description: Описание (например, "стрижет быстро и качественно")

        Returns:
            Подходящие специалисты
        """
        # TODO: Реализовать семантический поиск по контекстам
        pass


def main():
    """Пример использования"""
    # Загрузка данных
    reviews = pd.read_csv('reviews_full.csv')
    places = pd.read_csv('places.csv')

    # Добавляем названия заведений к отзывам
    reviews = reviews.merge(
        places[['id', 'name', 'category']],
        left_on='place_id',
        right_on='id',
        how='left'
    )
    reviews.rename(columns={'name': 'place_name'}, inplace=True)

    # Инициализация трекера
    tracker = SpecialistTracker()

    # 1. Построение базы данных специалистов
    print("=== ПОСТРОЕНИЕ БАЗЫ ДАННЫХ СПЕЦИАЛИСТОВ ===\n")
    specialist_db = tracker.build_specialist_database(reviews)
    print(f"Найдено {len(specialist_db)} специалистов")
    print("\nТоп-10 специалистов по упоминаниям:")
    print(specialist_db.head(10)[['name', 'type', 'mentions', 'latest_place']])

    # 2. Поиск конкретного специалиста
    print("\n=== ПОИСК СПЕЦИАЛИСТА ===\n")
    search_name = "Александр"  # Пример
    results = tracker.find_specialist(search_name, specialist_db, threshold=0.6)

    if results:
        print(f"Найдено совпадений: {len(results)}")
        for result in results[:5]:
            print(f"\n{result['name']} ({result['type']})")
            print(f"  Схожесть: {result['similarity']:.2f}")
            print(f"  Работает в: {', '.join(result['current_places'][:3])}")
            print(f"  Упоминаний: {result['mentions']}")
    else:
        print("Специалисты не найдены")

    # 3. История перемещений
    if results:
        top_specialist = results[0]['name']
        print(f"\n=== ИСТОРИЯ РАБОТЫ: {top_specialist} ===\n")
        history = tracker.track_specialist_movement(top_specialist, reviews)

        for workplace in history:
            print(f"{workplace['place_name']}: {workplace['period']}")


if __name__ == "__main__":
    main()
