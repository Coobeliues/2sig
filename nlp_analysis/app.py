"""
Streamlit интерфейс для семантического поиска заведений
"""

import streamlit as st
import pandas as pd
from semantic_search import SemanticSearch
import plotly.express as px


@st.cache_resource
def load_search_engine():
    """Загрузка и кэширование поисковой системы"""
    search_engine = SemanticSearch(model_name='sentence-transformers/LaBSE')
    search_engine.load_data(
        reviews_path='reviews_full.csv',
        places_path='places.csv'
    )
    search_engine.create_embeddings(
        batch_size=32,
        cache_path='cache/embeddings.pkl'
    )
    search_engine.build_index()
    return search_engine


def main():
    st.set_page_config(
        page_title="2GIS Smart Search",
        page_icon="🔍",
        layout="wide"
    )

    st.title("🔍 Умный поиск заведений 2GIS")
    st.markdown("""
    Найдите идеальное заведение по описанию! Просто опишите, что вы ищете,
    и система найдет лучшие варианты на основе анализа отзывов.
    """)

    # Загрузка поисковой системы
    with st.spinner("Загрузка модели и данных..."):
        search_engine = load_search_engine()

    # Боковая панель с настройками
    with st.sidebar:
        st.header("⚙️ Настройки поиска")

        top_k = st.slider(
            "Количество результатов",
            min_value=1,
            max_value=20,
            value=10
        )

        min_reviews = st.slider(
            "Минимум релевантных отзывов",
            min_value=1,
            max_value=10,
            value=3,
            help="Заведения с меньшим количеством релевантных отзывов будут исключены"
        )

        aggregation = st.selectbox(
            "Метод ранжирования",
            options=['weighted', 'mean', 'max'],
            format_func=lambda x: {
                'weighted': 'Взвешенный (рекомендуется)',
                'mean': 'Средний балл',
                'max': 'Максимальное сходство'
            }[x]
        )

        st.markdown("---")
        st.markdown("### 💡 Примеры запросов")
        example_queries = [
            "уютное кафе с вкусным кофе",
            "тихое место для работы",
            "ресторан с романтической атмосферой",
            "недорогое кафе с хорошей едой",
            "место для семейного ужина",
            "модный бар с коктейлями",
            "заведение с живой музыкой",
            "кофейня с десертами"
        ]

        for example in example_queries:
            if st.button(example, key=example):
                st.session_state.query = example

    # Основная область поиска
    query = st.text_input(
        "Опишите заведение, которое вы ищете:",
        value=st.session_state.get('query', ''),
        placeholder="Например: уютное кафе с вкусным кофе и быстрым обслуживанием"
    )

    if st.button("🔍 Найти", type="primary") or query:
        if not query:
            st.warning("Пожалуйста, введите запрос")
            return

        with st.spinner("Поиск заведений..."):
            results = search_engine.search_places(
                query=query,
                top_k=top_k,
                min_reviews=min_reviews,
                aggregation=aggregation
            )

        if len(results) == 0:
            st.warning("По вашему запросу ничего не найдено. Попробуйте изменить параметры поиска.")
            return

        st.success(f"Найдено {len(results)} заведений")

        # Показываем результаты
        for idx, row in results.iterrows():
            with st.expander(
                f"**{idx + 1}. {row['name']}** ⭐ {row['rating']:.1f} | Релевантность: {row['final_score']:.3f}",
                expanded=(idx == 0)
            ):
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.markdown(f"**📍 Адрес:** {row['address']}")
                    st.markdown(f"**🏷️ Категория:** {row['category']}")
                    st.markdown(f"**💬 Релевантных отзывов:** {int(row['review_count'])}")

                with col2:
                    # Метрики
                    st.metric("Рейтинг", f"{row['rating']:.1f}/5.0")
                    st.metric("Релевантность", f"{row['final_score']:.3f}")

                # Показываем самые релевантные отзывы
                st.markdown("#### 💬 Релевантные отзывы:")
                highlights = search_engine.get_place_highlights(
                    place_id=row['place_id'],
                    query=query,
                    top_k=3
                )

                for i, review in enumerate(highlights, 1):
                    st.markdown(f"**{i}.** {review}")

                st.markdown("---")

        # Визуализация
        st.markdown("### 📊 Анализ результатов")

        col1, col2 = st.columns(2)

        with col1:
            # График рейтинга vs релевантности
            fig = px.scatter(
                results,
                x='rating',
                y='final_score',
                size='review_count',
                hover_data=['name'],
                title='Рейтинг vs Релевантность',
                labels={
                    'rating': 'Рейтинг 2GIS',
                    'final_score': 'Релевантность запросу',
                    'review_count': 'Кол-во отзывов'
                }
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Распределение по категориям
            category_counts = results['category'].value_counts().head(10)
            fig = px.bar(
                x=category_counts.values,
                y=category_counts.index,
                orientation='h',
                title='Топ категории в результатах',
                labels={'x': 'Количество', 'y': 'Категория'}
            )
            st.plotly_chart(fig, use_container_width=True)

    # Статистика в футере
    st.markdown("---")
    st.markdown(f"""
    <div style='text-align: center; color: gray;'>
    📊 База данных: {len(search_engine.reviews_df):,} отзывов |
    {len(search_engine.places_df):,} заведений
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
