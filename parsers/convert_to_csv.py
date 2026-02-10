"""
Конвертация JSON -> CSV и проверка полноты данных
"""
import json
import csv
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Загрузка данных
print("📂 Загружаю данные...")
with open('2gis_mass_reviews_almaty_20251006_163719.json', 'r', encoding='utf-8') as f:
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

short_reviews = [r for r in all_reviews if len(r['text']) < 50]
print(f"   Коротких (<50 символов): {len(short_reviews)} ({len(short_reviews) / len(all_reviews) * 100:.1f}%)")

# Показываем примеры
print(f"\n📝 Примеры коротких отзывов:")
for i, r in enumerate(short_reviews[:3], 1):
    print(f"   {i}. ({len(r['text'])} символов) \"{r['text']}\"")

print(f"\n📝 Примеры длинных отзывов:")
long_reviews = sorted(all_reviews, key=lambda r: len(r['text']), reverse=True)[:3]
for i, r in enumerate(long_reviews, 1):
    print(f"   {i}. ({len(r['text'])} символов) \"{r['text'][:100]}...\"")

# Конвертация в CSV
print("\n" + "=" * 70)
print("📄 КОНВЕРТАЦИЯ В CSV")
print("=" * 70)

# Создаем два CSV файла:
# 1. С информацией о заведениях
# 2. С отзывами (развернутый формат)

# CSV 1: Заведения
print("\n📁 Создаю places.csv (информация о заведениях)...")
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

print(f"✅ Сохранено {len(data)} заведений в places.csv")

# CSV 2: Отзывы (развернутый формат - каждый отзыв в отдельной строке)
print("\n📁 Создаю reviews.csv (все отзывы)...")
with open('reviews.csv', 'w', encoding='utf-8', newline='') as f:
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
                review['date'],
                review['is_verified']
            ])

print(f"✅ Сохранено {total_collected:,} отзывов в reviews.csv")

# CSV 3: Упрощенный формат (только текст и метки)
print("\n📁 Создаю reviews_simple.csv (упрощенный для NLP)...")
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

print(f"✅ Сохранено {total_collected:,} отзывов в reviews_simple.csv")

# Финальная статистика
print("\n" + "=" * 70)
print("✅ ГОТОВО!")
print("=" * 70)

print(f"""
📁 Созданные файлы:

1. places.csv ({len(data)} строк)
   - Информация о заведениях

2. reviews.csv ({total_collected:,} строк)
   - Полная информация об отзывах
   - Включает данные о заведении

3. reviews_simple.csv ({total_collected:,} строк)
   - Упрощенный формат для NLP
   - Только: текст, рейтинг, категория

💡 Рекомендация для NLP:
   Используйте reviews_simple.csv для быстрого старта
""")

# Проверка на наличие лимита по длине
print("\n" + "=" * 70)
print("🔍 ПРОВЕРКА ЛИМИТА ДЛИНЫ ТЕКСТА")
print("=" * 70)

truncated = [r for r in all_reviews if r['text'].endswith('...') or len(r['text']) == 500]
print(f"\nОбрезанных текстов (500 символов): {len(truncated)}")
if truncated:
    print(f"Процент обрезанных: {len(truncated) / len(all_reviews) * 100:.2f}%")
    print(f"\nПримеры обрезанных текстов:")
    for i, r in enumerate(truncated[:3], 1):
        print(f"  {i}. Длина: {len(r['text'])} - \"{r['text'][-80:]}\"")
else:
    print("✅ Обрезанных текстов не обнаружено!")

print("\n✅ Все проверки завершены!")
