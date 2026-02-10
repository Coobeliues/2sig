"""
Продвинутая аналитика отзывов:
- Детекция спама и фейковых отзывов
- Aspect-Based Sentiment Analysis (ABSA)
- Named Entity Recognition (NER) для извлечения блюд и услуг
- Тематическое моделирование
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple
import re
from collections import Counter
from datetime import datetime
import spacy
from textblob import TextBlob


class SpamDetector:
    """
    Детектор спама и подозрительных отзывов
    """

    def __init__(self):
        self.suspicious_patterns = [
            r'(whatsapp|telegram|viber).*\d{10,}',  # Контакты
            r'(http|www\.)',  # Ссылки
            r'(скидка|промокод|акция).*\d+%',  # Рекламные акции
        ]

    def calculate_text_entropy(self, text: str) -> float:
        """Вычисление энтропии текста (низкая энтропия = подозрительно)"""
        if not text:
            return 0.0

        # Подсчет частоты символов
        char_freq = Counter(text.lower())
        total_chars = len(text)

        # Вычисление энтропии Шеннона
        entropy = 0.0
        for count in char_freq.values():
            probability = count / total_chars
            if probability > 0:
                entropy -= probability * np.log2(probability)

        return entropy

    def detect_repetitive_phrases(self, text: str, min_length: int = 10) -> int:
        """Обнаружение повторяющихся фраз"""
        words = text.lower().split()
        if len(words) < min_length:
            return 0

        phrases = []
        for i in range(len(words) - min_length + 1):
            phrase = ' '.join(words[i:i + min_length])
            phrases.append(phrase)

        # Подсчет уникальности
        unique_ratio = len(set(phrases)) / len(phrases) if phrases else 1.0
        return 1 - unique_ratio  # Высокое значение = много повторов

    def check_suspicious_patterns(self, text: str) -> bool:
        """Проверка на подозрительные паттерны"""
        for pattern in self.suspicious_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def analyze_review(self, review: Dict) -> Dict:
        """
        Комплексный анализ отзыва на подозрительность

        Returns:
            Dict с метриками подозрительности
        """
        text = review.get('review_text', '')
        rating = review.get('rating', 3)

        metrics = {
            'text_entropy': self.calculate_text_entropy(text),
            'repetitiveness': self.detect_repetitive_phrases(text),
            'has_suspicious_patterns': self.check_suspicious_patterns(text),
            'text_length': len(text),
            'is_very_short': len(text) < 20,
            'is_very_long': len(text) > 2000,
            'extreme_rating': rating in [1, 5],  # Крайние оценки чаще фейковые
        }

        # Общий скор подозрительности (0-1)
        spam_score = 0.0

        if metrics['text_entropy'] < 3.0:  # Низкая энтропия
            spam_score += 0.3
        if metrics['repetitiveness'] > 0.5:  # Много повторов
            spam_score += 0.3
        if metrics['has_suspicious_patterns']:
            spam_score += 0.4
        if metrics['is_very_short'] and metrics['extreme_rating']:
            spam_score += 0.2
        if metrics['is_very_long']:  # Слишком длинные часто спам
            spam_score += 0.1

        metrics['spam_score'] = min(spam_score, 1.0)
        metrics['is_suspicious'] = spam_score > 0.5

        return metrics

    def detect_place_manipulation(self, place_reviews: pd.DataFrame) -> Dict:
        """
        Анализ заведения на накрутку отзывов

        Args:
            place_reviews: DataFrame отзывов одного заведения

        Returns:
            Метрики подозрительности заведения
        """
        if len(place_reviews) < 5:
            return {'manipulation_score': 0.0, 'warning': 'Недостаточно данных'}

        # Анализ временных паттернов
        if 'date' in place_reviews.columns:
            place_reviews['date'] = pd.to_datetime(place_reviews['date'])
            # Группировка по дням
            daily_reviews = place_reviews.groupby(place_reviews['date'].dt.date).size()
            # Подозрительно, если много отзывов в один день
            suspicious_days = (daily_reviews > 5).sum()
        else:
            suspicious_days = 0

        # Анализ распределения оценок
        ratings = place_reviews['rating'].values
        rating_variance = np.var(ratings)
        five_star_ratio = (ratings == 5).sum() / len(ratings)

        # Анализ текстов
        spam_scores = []
        for _, review in place_reviews.iterrows():
            metrics = self.analyze_review(review.to_dict())
            spam_scores.append(metrics['spam_score'])

        avg_spam_score = np.mean(spam_scores)

        # Общий скор накрутки
        manipulation_score = 0.0

        if suspicious_days > 2:  # Всплески отзывов
            manipulation_score += 0.3
        if rating_variance < 0.5 and five_star_ratio > 0.8:  # Только 5 звезд
            manipulation_score += 0.4
        if avg_spam_score > 0.4:  # Много подозрительных отзывов
            manipulation_score += 0.3

        return {
            'manipulation_score': min(manipulation_score, 1.0),
            'suspicious_days': suspicious_days,
            'five_star_ratio': five_star_ratio,
            'avg_spam_score': avg_spam_score,
            'is_manipulated': manipulation_score > 0.5
        }


class AspectExtractor:
    """
    Извлечение аспектов и их тональности из отзывов
    """

    def __init__(self):
        # Предопределенные аспекты для ресторанов/кафе
        self.aspects = {
            'еда': ['еда', 'блюд', 'кухн', 'вкус', 'меню', 'порци'],
            'сервис': ['сервис', 'обслуж', 'официант', 'персонал', 'внимател'],
            'атмосфера': ['атмосфер', 'уют', 'интерьер', 'обстанов', 'дизайн', 'музык'],
            'цена': ['цен', 'дорог', 'дешев', 'стоимост', 'недорог', 'доступн'],
            'чистота': ['чист', 'грязн', 'порядок', 'опрятн'],
            'скорость': ['быстр', 'долго', 'ожидан', 'скор'],
        }

    def extract_aspects(self, text: str) -> List[str]:
        """Извлечение упомянутых аспектов"""
        text_lower = text.lower()
        found_aspects = []

        for aspect, keywords in self.aspects.items():
            for keyword in keywords:
                if keyword in text_lower:
                    found_aspects.append(aspect)
                    break

        return found_aspects

    def get_aspect_sentiment(self, text: str, aspect: str) -> float:
        """
        Определение тональности для конкретного аспекта

        Returns:
            Sentiment score от -1 (негативный) до 1 (позитивный)
        """
        # Находим предложения, содержащие аспект
        sentences = re.split(r'[.!?]', text.lower())
        aspect_sentences = []

        keywords = self.aspects.get(aspect, [aspect])
        for sentence in sentences:
            if any(keyword in sentence for keyword in keywords):
                aspect_sentences.append(sentence)

        if not aspect_sentences:
            return 0.0

        # Анализ тональности через TextBlob (базовый подход)
        sentiments = []
        for sentence in aspect_sentences:
            blob = TextBlob(sentence)
            sentiments.append(blob.sentiment.polarity)

        return np.mean(sentiments) if sentiments else 0.0

    def analyze_review(self, text: str) -> Dict:
        """Полный анализ аспектов в отзыве"""
        aspects = self.extract_aspects(text)
        result = {}

        for aspect in aspects:
            sentiment = self.get_aspect_sentiment(text, aspect)
            result[aspect] = {
                'sentiment': sentiment,
                'label': 'позитивный' if sentiment > 0.2 else (
                    'негативный' if sentiment < -0.2 else 'нейтральный'
                )
            }

        return result

    def aggregate_place_aspects(self, place_reviews: pd.DataFrame) -> Dict:
        """Агрегация аспектов по всем отзывам заведения"""
        aspect_sentiments = {aspect: [] for aspect in self.aspects.keys()}

        for _, review in place_reviews.iterrows():
            aspects = self.analyze_review(review['review_text'])
            for aspect, data in aspects.items():
                aspect_sentiments[aspect].append(data['sentiment'])

        # Вычисляем средние значения
        result = {}
        for aspect, sentiments in aspect_sentiments.items():
            if sentiments:
                result[aspect] = {
                    'avg_sentiment': np.mean(sentiments),
                    'mention_count': len(sentiments),
                    'positive_ratio': sum(1 for s in sentiments if s > 0.2) / len(sentiments)
                }

        return result


class DishExtractor:
    """
    Извлечение названий блюд и напитков из отзывов (простой NER)
    """

    def __init__(self):
        # Попытка загрузить spaCy модель для русского
        try:
            self.nlp = spacy.load("ru_core_news_sm")
        except:
            print("Модель ru_core_news_sm не найдена. Установите: python -m spacy download ru_core_news_sm")
            self.nlp = None

        # Ключевые слова-маркеры блюд
        self.food_markers = [
            'попробовал', 'заказал', 'взял', 'съел',
            'вкусный', 'блюдо', 'порция', 'меню'
        ]

    def extract_dishes(self, text: str) -> List[str]:
        """
        Извлечение названий блюд из текста

        Простой подход: ищем существительные рядом с маркерами еды
        """
        if not self.nlp:
            return []

        doc = self.nlp(text.lower())
        dishes = []

        # Поиск существительных после маркеров
        for i, token in enumerate(doc):
            if token.lemma_ in self.food_markers:
                # Смотрим на следующие 3 слова
                for j in range(i + 1, min(i + 4, len(doc))):
                    if doc[j].pos_ == 'NOUN':
                        dishes.append(doc[j].text)

        return list(set(dishes))

    def get_popular_dishes(self, reviews: pd.DataFrame, top_k: int = 20) -> List[Tuple[str, int]]:
        """Найти самые популярные блюда в отзывах"""
        all_dishes = []

        for _, review in reviews.iterrows():
            dishes = self.extract_dishes(review['review_text'])
            all_dishes.extend(dishes)

        # Подсчет частоты
        dish_counts = Counter(all_dishes)
        return dish_counts.most_common(top_k)


class TrendAnalyzer:
    """
    Анализ трендов и изменений во времени
    """

    def __init__(self):
        pass

    def analyze_rating_trend(self, place_reviews: pd.DataFrame, window: int = 30) -> Dict:
        """
        Анализ тренда рейтинга заведения

        Args:
            place_reviews: Отзывы заведения с полем 'date'
            window: Размер окна в днях для сглаживания

        Returns:
            Информация о тренде
        """
        if 'date' not in place_reviews.columns or len(place_reviews) < 10:
            return {'trend': 'unknown', 'reason': 'Недостаточно данных'}

        # Сортировка по дате
        df = place_reviews.sort_values('date').copy()
        df['date'] = pd.to_datetime(df['date'])

        # Скользящее среднее
        df['rating_ma'] = df['rating'].rolling(window=min(window, len(df)//2)).mean()

        # Сравнение первой и последней трети
        first_third = df.head(len(df) // 3)['rating'].mean()
        last_third = df.tail(len(df) // 3)['rating'].mean()

        delta = last_third - first_third

        if delta > 0.5:
            trend = 'improving'
            description = 'Качество улучшается'
        elif delta < -0.5:
            trend = 'declining'
            description = 'Качество ухудшается'
        else:
            trend = 'stable'
            description = 'Стабильное качество'

        return {
            'trend': trend,
            'description': description,
            'delta': delta,
            'current_avg': last_third,
            'previous_avg': first_third
        }

    def detect_seasonal_patterns(self, reviews: pd.DataFrame) -> Dict:
        """Анализ сезонных паттернов"""
        if 'date' not in reviews.columns:
            return {}

        reviews['date'] = pd.to_datetime(reviews['date'])
        reviews['month'] = reviews['date'].dt.month

        # Средний рейтинг по месяцам
        monthly_avg = reviews.groupby('month')['rating'].mean()

        best_month = monthly_avg.idxmax()
        worst_month = monthly_avg.idxmin()

        month_names = {
            1: 'январь', 2: 'февраль', 3: 'март', 4: 'апрель',
            5: 'май', 6: 'июнь', 7: 'июль', 8: 'август',
            9: 'сентябрь', 10: 'октябрь', 11: 'ноябрь', 12: 'декабрь'
        }

        return {
            'best_month': month_names.get(best_month),
            'worst_month': month_names.get(worst_month),
            'monthly_ratings': monthly_avg.to_dict()
        }


def main():
    """Примеры использования"""
    # Загрузка данных
    reviews = pd.read_csv('reviews_full.csv')

    # 1. Детекция спама
    print("=== АНАЛИЗ СПАМА ===\n")
    spam_detector = SpamDetector()

    sample_review = reviews.iloc[0].to_dict()
    spam_metrics = spam_detector.analyze_review(sample_review)
    print(f"Метрики подозрительности: {spam_metrics}")

    # Анализ заведения на накрутку
    place_id = reviews.iloc[0]['place_id']
    place_reviews = reviews[reviews['place_id'] == place_id]
    manipulation = spam_detector.detect_place_manipulation(place_reviews)
    print(f"\nАнализ накрутки для заведения {place_id}: {manipulation}")

    # 2. Анализ аспектов
    print("\n=== АНАЛИЗ АСПЕКТОВ ===\n")
    aspect_extractor = AspectExtractor()

    sample_text = place_reviews.iloc[0]['review_text']
    aspects = aspect_extractor.analyze_review(sample_text)
    print(f"Аспекты в отзыве: {aspects}")

    place_aspects = aspect_extractor.aggregate_place_aspects(place_reviews)
    print(f"\nАгрегированные аспекты заведения:\n{place_aspects}")

    # 3. Извлечение блюд
    print("\n=== ПОПУЛЯРНЫЕ БЛЮДА ===\n")
    dish_extractor = DishExtractor()
    popular_dishes = dish_extractor.get_popular_dishes(place_reviews, top_k=10)
    print(f"Топ блюда: {popular_dishes}")

    # 4. Анализ трендов
    print("\n=== АНАЛИЗ ТРЕНДОВ ===\n")
    trend_analyzer = TrendAnalyzer()
    trend = trend_analyzer.analyze_rating_trend(place_reviews)
    print(f"Тренд рейтинга: {trend}")


if __name__ == "__main__":
    main()
