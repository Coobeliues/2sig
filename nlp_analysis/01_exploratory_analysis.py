"""
Exploratory Data Analysis для отзывов 2GIS
Анализ распределений, статистика, визуализации
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from collections import Counter
import re

# Настройка визуализации
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['font.family'] = 'DejaVu Sans'
sns.set_style('whitegrid')

def load_data():
    """Загрузка датасетов"""
    print("Загрузка данных...")
    reviews = pd.read_csv('reviews_full.csv')
    places = pd.read_csv('places.csv')
    return reviews, places

def basic_stats(reviews, places):
    """Базовая статистика"""
    print("\n" + "="*60)
    print("БАЗОВАЯ СТАТИСТИКА")
    print("="*60)

    print(f"\n📊 Общие метрики:")
    print(f"  Всего отзывов: {len(reviews):,}")
    print(f"  Всего заведений: {len(places):,}")
    print(f"  Отзывов на заведение (среднее): {len(reviews)/len(places):.1f}")

    print(f"\n📝 Статистика текстов:")
    print(f"  Средняя длина: {reviews['text_length'].mean():.1f} символов")
    print(f"  Медианная длина: {reviews['text_length'].median():.0f} символов")
    print(f"  Макс длина: {reviews['text_length'].max():,} символов")
    print(f"  Мин длина: {reviews['text_length'].min():,} символов")

    print(f"\n⭐ Рейтинги:")
    rating_dist = reviews['rating'].value_counts().sort_index()
    for rating, count in rating_dist.items():
        pct = (count/len(reviews))*100
        print(f"  {rating} звёзд: {count:,} ({pct:.1f}%)")
    print(f"  Средний рейтинг: {reviews['rating'].mean():.2f}")

    print(f"\n✅ Верификация:")
    verified = reviews['is_verified'].sum()
    print(f"  Верифицированных: {verified:,} ({verified/len(reviews)*100:.1f}%)")

def category_analysis(reviews):
    """Анализ по категориям"""
    print("\n" + "="*60)
    print("АНАЛИЗ ПО КАТЕГОРИЯМ")
    print("="*60)

    cat_stats = reviews.groupby('category').agg({
        'text': 'count',
        'rating': 'mean',
        'text_length': 'mean'
    }).round(2)
    cat_stats.columns = ['Количество', 'Средний рейтинг', 'Средняя длина']
    cat_stats = cat_stats.sort_values('Количество', ascending=False)

    print("\n" + cat_stats.to_string())

def text_analysis(reviews):
    """Анализ текстов"""
    print("\n" + "="*60)
    print("АНАЛИЗ ТЕКСТОВ")
    print("="*60)

    # Подсчет слов
    reviews['word_count'] = reviews['text'].apply(lambda x: len(str(x).split()))

    print(f"\n📊 Статистика слов:")
    print(f"  Среднее кол-во слов: {reviews['word_count'].mean():.1f}")
    print(f"  Медиана слов: {reviews['word_count'].median():.0f}")

    # Частотный анализ слов
    all_words = []
    for text in reviews['text'].astype(str):
        words = re.findall(r'\b[а-яА-ЯёЁ]{3,}\b', text.lower())
        all_words.extend(words)

    word_freq = Counter(all_words)
    print(f"\n🔤 Топ-20 слов:")
    for word, count in word_freq.most_common(20):
        print(f"  {word}: {count:,}")

def sentiment_patterns(reviews):
    """Базовый анализ тональности по ключевым словам"""
    print("\n" + "="*60)
    print("ПАТТЕРНЫ ТОНАЛЬНОСТИ")
    print("="*60)

    positive_words = ['вкусно', 'отлично', 'хорошо', 'прекрасно', 'уютно',
                      'понравилось', 'рекомендую', 'замечательно', 'превосходно']
    negative_words = ['плохо', 'невкусно', 'ужасно', 'разочаровал',
                      'не рекомендую', 'грязно', 'холодно', 'дорого']

    def count_sentiment_words(text, words_list):
        text_lower = str(text).lower()
        return sum(1 for word in words_list if word in text_lower)

    reviews['positive_words'] = reviews['text'].apply(
        lambda x: count_sentiment_words(x, positive_words)
    )
    reviews['negative_words'] = reviews['text'].apply(
        lambda x: count_sentiment_words(x, negative_words)
    )

    print(f"\n😊 Позитивные слова:")
    print(f"  Отзывов с позитивными словами: {(reviews['positive_words'] > 0).sum():,}")
    print(f"  Среднее количество: {reviews['positive_words'].mean():.2f}")

    print(f"\n😞 Негативные слова:")
    print(f"  Отзывов с негативными словами: {(reviews['negative_words'] > 0).sum():,}")
    print(f"  Среднее количество: {reviews['negative_words'].mean():.2f}")

    # Корреляция с рейтингом
    pos_corr = reviews[['rating', 'positive_words']].corr().iloc[0, 1]
    neg_corr = reviews[['rating', 'negative_words']].corr().iloc[0, 1]

    print(f"\n📈 Корреляция с рейтингом:")
    print(f"  Позитивные слова: {pos_corr:.3f}")
    print(f"  Негативные слова: {neg_corr:.3f}")

def create_visualizations(reviews):
    """Создание визуализаций"""
    print("\n" + "="*60)
    print("СОЗДАНИЕ ВИЗУАЛИЗАЦИЙ")
    print("="*60)

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))

    # 1. Распределение рейтингов
    reviews['rating'].value_counts().sort_index().plot(
        kind='bar', ax=axes[0, 0], color='steelblue'
    )
    axes[0, 0].set_title('Распределение рейтингов', fontsize=14, weight='bold')
    axes[0, 0].set_xlabel('Рейтинг')
    axes[0, 0].set_ylabel('Количество отзывов')

    # 2. Распределение длины текста
    axes[0, 1].hist(reviews['text_length'], bins=50, color='coral', edgecolor='black')
    axes[0, 1].set_title('Распределение длины отзывов', fontsize=14, weight='bold')
    axes[0, 1].set_xlabel('Длина (символы)')
    axes[0, 1].set_ylabel('Количество')
    axes[0, 1].set_xlim(0, 1000)

    # 3. Отзывы по категориям
    cat_counts = reviews['category'].value_counts()
    axes[1, 0].barh(range(len(cat_counts)), cat_counts.values, color='lightgreen')
    axes[1, 0].set_yticks(range(len(cat_counts)))
    axes[1, 0].set_yticklabels(cat_counts.index)
    axes[1, 0].set_title('Количество отзывов по категориям', fontsize=14, weight='bold')
    axes[1, 0].set_xlabel('Количество отзывов')

    # 4. Средний рейтинг по категориям
    cat_ratings = reviews.groupby('category')['rating'].mean().sort_values()
    axes[1, 1].barh(range(len(cat_ratings)), cat_ratings.values, color='gold')
    axes[1, 1].set_yticks(range(len(cat_ratings)))
    axes[1, 1].set_yticklabels(cat_ratings.index)
    axes[1, 1].set_title('Средний рейтинг по категориям', fontsize=14, weight='bold')
    axes[1, 1].set_xlabel('Средний рейтинг')
    axes[1, 1].set_xlim(0, 5)

    plt.tight_layout()
    plt.savefig('eda_visualizations.png', dpi=300, bbox_inches='tight')
    print("\n✅ Визуализации сохранены: eda_visualizations.png")

def main():
    """Главная функция"""
    print("\n🔍 АНАЛИЗ ДАННЫХ 2GIS ОТЗЫВОВ")

    reviews, places = load_data()

    basic_stats(reviews, places)
    category_analysis(reviews)
    text_analysis(reviews)
    sentiment_patterns(reviews)
    create_visualizations(reviews)

    print("\n" + "="*60)
    print("✅ АНАЛИЗ ЗАВЕРШЕН")
    print("="*60)

if __name__ == "__main__":
    main()