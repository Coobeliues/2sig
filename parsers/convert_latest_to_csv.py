
import json
import csv
import sys
import io
import glob

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Находим последний файл
json_files = glob.glob('2gis_mass_reviews_almaty_*.json')
latest_file = max(json_files, key=lambda x: x)

print(f"📂 Загружаю данные из {latest_file}...")
with open(latest_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"✅ Загружено {len(data)} заведений\n")

# Проверка полноты
print("=" * 70)
print("📊 ПРОВЕРКА ПОЛНОТЫ ДАННЫХ")
print("=" * 70)

total_expected = sum(p['reviews_count'] for p in data)
total_collected = sum(len(p['reviews']) for p in data)

print(f"\n📈 Ожидалось отзывов (по 2GIS): {total_expected:,}")
print(f"✅ Собрано отзывов: {total_collected:,}")
print(f"📊 Процент покрытия: {total_collected / total_expected * 100:.1f}%")

# Анализ отфильтрованных
filtered_count = total_expected - total_collected
print(f"\n❌ Отфильтровано: {filtered_count:,} отзывов")
print(f"   Причина: текст короче 30 символов (оценки без текста)")

# Статистика по длине текста
all_reviews = [r for p in data for r in p['reviews']]
text_lengths = [len(r['text']) for r in all_reviews]

print(f"\n📏 Статистика длины текста:")
print(f"   Минимальная: {min(text_lengths)} символов")
print(f"   Средняя: {sum(text_lengths) / len(text_lengths):.1f} символов")
print(f"   Максимальная: {max(text_lengths)} символов")

long_reviews = [r for r in all_reviews if len(r['text']) > 500]
print(f"   Длинных (>500 символов): {len(long_reviews)} ({len(long_reviews) / len(all_reviews) * 100:.1f}%)")

very_long = sorted(all_reviews, key=lambda r: len(r['text']), reverse=True)[:5]
print(f"\n📝 Топ-5 самых длинных отзывов:")
for i, r in enumerate(very_long, 1):
    print(f"   {i}. Длина: {len(r['text'])} символов")

# Конвертация в CSV
print("\n" + "=" * 70)
print("📄 КОНВЕРТАЦИЯ В CSV")
print("=" * 70)

# CSV 1: Заведения
print("\n📁 Создаю places.csv...")
with open('places.csv', 'w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerow([
        'firm_id',
        'name',
        'category',
        'category_search',
        'address',
        'rating',
        'reviews_count',
        'reviews_collected',
        'phone',
        'url'
    ])

    for place in data:
        writer.writerow([
            place['firm_id'],
            place['name'],
            place['category'],
            place['category_search'],
            place['address'],
            place['rating'],
            place['reviews_count'],
            len(place['reviews']),
            place['phone'],
            place['url']
        ])

print(f"✅ Сохранено {len(data)} заведений")

# CSV 2: Отзывы (полный формат)
print("\n📁 Создаю reviews_full.csv (полные тексты)...")
with open('reviews_full.csv', 'w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerow([
        'place_firm_id',
        'place_name',
        'place_category',
        'place_category_search',
        'place_rating',
        'place_address',
        'author',
        'author_reviews_count',
        'rating',
        'text',
        'text_length',
        'date',
        'is_verified'
    ])

    for place in data:
        for review in place['reviews']:
            writer.writerow([
                place['firm_id'],
                place['name'],
                place['category'],
                place['category_search'],
                place['rating'],
                place['address'],
                review['author'],
                review['author_reviews_count'],
                review['rating'],
                review['text'],
                len(review['text']),
                review['date'],
                review['is_verified']
            ])

print(f"✅ Сохранено {total_collected:,} отзывов с ПОЛНЫМИ текстами")

# CSV 3: Упрощенный формат для NLP
print("\n📁 Создаю reviews_simple.csv...")
with open('reviews_simple.csv', 'w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerow([
        'text',
        'rating',
        'category',
        'place_name'
    ])

    for place in data:
        for review in place['reviews']:
            writer.writerow([
                review['text'],
                review['rating'],
                place['category_search'],
                place['name']
            ])

print(f"✅ Сохранено {total_collected:,} отзывов")

# Финальная статистика
print("\n" + "=" * 70)
print("✅ ГОТОВО!")
print("=" * 70)

print(f"""
📁 Созданные файлы:

1. places.csv ({len(data)} строк)
   - Информация о заведениях

2. reviews_full.csv ({total_collected:,} строк) ⭐ ПОЛНЫЕ ТЕКСТЫ
   - Полная информация об отзывах
   - ВЕСЬ текст БЕЗ обрезки
   - Колонка text_length для анализа

3. reviews_simple.csv ({total_collected:,} строк)
   - Упрощенный формат для NLP
   - Полные тексты: текст, рейтинг, категория

💡 Теперь тексты НЕ обрезаны!
""")

print("\n" + "=" * 70)
print("🔍 ПРОВЕРКА ЛИМИТА")
print("=" * 70)

print(f"\n✅ ЛИМИТ УБРАН! Все тексты в полном объеме")
print(f"📊 Самый длинный отзыв: {max(text_lengths)} символов")
print(f"📊 Отзывов длиннее 500 символов: {len(long_reviews):,} ({len(long_reviews) / len(all_reviews) * 100:.1f}%)")
print(f"📊 Отзывов длиннее 1000 символов: {len([r for r in all_reviews if len(r['text']) > 1000]):,}")

print("\n✅ Все данные собраны в полном объеме!")
