# 2GIS Semantic Search

Семантический поиск заведений по отзывам 2GIS (Алматы). Находит кафе, рестораны и другие заведения по естественному описанию на русском и казахском языках.

## Как работает

1. **Парсер** (`parsers/`) собирает отзывы с 2GIS через Selenium + API
2. **Подготовка** (`2v/step1_prepare.py`) создаёт эмбеддинги через LaBSE и строит FAISS-индекс
3. **Поиск** (`2v/step2_search.py`) — семантический поиск + sentiment-анализ для ранжирования
4. **Веб-интерфейс** (`2v/app.py`) — Streamlit UI

## Стек

- **LaBSE** — мультиязычные эмбеддинги (ru/kz)
- **FAISS** — быстрый поиск по векторам
- **rubert-base-cased-sentiment** — sentiment-анализ отзывов
- **Streamlit** — веб-интерфейс

## Запуск

```bash
pip install -r requirements.txt

# 1. Собрать отзывы (нужен Chrome)
cd parsers
python parser_mass_collection.py
python convert_latest_to_csv.py

# 2. Положить CSV в 2v/data/
mkdir -p 2v/data
cp places.csv reviews.csv 2v/data/

# 3. Создать эмбеддинги и индекс
cd 2v
python step1_prepare.py

# 4. Запуск
streamlit run app.py
# или CLI: python step2_search.py
```

## Структура

```
2v/
├── app.py              # Streamlit веб-интерфейс
├── config.py           # Конфигурация (модель, пути, параметры)
├── step1_prepare.py    # Подготовка: эмбеддинги + FAISS индекс
├── step2_search.py     # Поисковый движок + sentiment
├── data/               # CSV данные (не в репо)
└── cache/              # Эмбеддинги, индекс (не в репо)

parsers/
├── parser_mass_collection.py  # Парсер отзывов 2GIS
├── convert_to_csv.py          # JSON → CSV
└── convert_latest_to_csv.py   # Конвертация последнего JSON
```
