"""
Запуск: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from step2_search import SemanticSearch
import config
import time


# Настройка страницы
st.set_page_config(
    page_title="2GIS Semantic Search",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)


@st.cache_resource
def load_search_engine():
    """Загрузка поисковой системы (кэшируется)"""
    try:
        return SemanticSearch()
    except FileNotFoundError as e:
        st.error(f"❌ Ошибка: {e}")
        st.info("💡 Сначала запустите подготовку данных: `python step1_prepare.py`")
        st.stop()


# Загрузка
with st.spinner("⏳ Загрузка модели и данных..."):
    search_engine = load_search_engine()


# Заголовок
st.title("🔍 Умный поиск заведений 2GIS")
st.markdown("""
Найдите идеальное заведение по описанию!
Система использует семантический поиск на основе анализа отзывов.
""")


# Боковая панель с настройками
with st.sidebar:
    st.header("⚙️ Настройки поиска")

    top_k = st.slider(
        "Количество результатов",
        min_value=1,
        max_value=20,
        value=10,
        help="Сколько заведений показывать в результатах"
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
            'mean': 'Средний score',
            'max': 'Максимальный score'
        }[x],
        help="Как комбинировать scores нескольких отзывов"
    )

    st.markdown("---")

    st.markdown("### 📊 Статистика")
    st.metric("Отзывов в базе", f"{len(search_engine.reviews_df):,}")
    st.metric("Заведений", f"{len(search_engine.places_df):,}")

    st.markdown("---")

    st.markdown("### 💡 Примеры запросов")
    example_queries = [
        "уютное кафе с вкусным кофе",
        "недорогой ресторан с большими порциями",
        "тихое место для работы с wifi",
        "романтическое место для свидания",
        "заведение с живой музыкой",
        "семейное кафе с детской зоной",
        "модный бар с коктейлями",
        "где поесть поздно ночью"
    ]

    for example in example_queries:
        if st.button(example, key=example, use_container_width=True):
            st.session_state.query = example


# Основная область поиска
st.markdown("---")

query = st.text_input(
    "🔍 Опишите, что вы ищете:",
    value=st.session_state.get('query', ''),
    placeholder="Например: уютное кафе с вкусным кофе и быстрым обслуживанием",
    help="Опишите заведение своими словами, система найдет подходящие варианты"
)

# Кнопка поиска
col1, col2, col3 = st.columns([1, 3, 1])
with col2:
    search_button = st.button("🔍 Найти заведения", type="primary", use_container_width=True)


# Выполнение поиска
if search_button or query:
    if not query:
        st.warning("⚠️ Пожалуйста, введите запрос")
    else:
        with st.spinner("⏳ Поиск заведений..."):
            start_time = time.time()

            results = search_engine.search_places(
                query=query,
                top_k=top_k,
                min_reviews=min_reviews,
                aggregation=aggregation
            )

            elapsed = time.time() - start_time

        if len(results) == 0:
            st.error("❌ По вашему запросу ничего не найдено")
            st.info("💡 Попробуйте:")
            st.markdown("""
            - Изменить запрос
            - Уменьшить "Минимум релевантных отзывов"
            - Использовать другие слова
            """)
        else:
            st.success(f"✅ Найдено {len(results)} заведений за {elapsed*1000:.0f}ms")

            # Табы для разных видов отображения
            tab1, tab2, tab3 = st.tabs(["📋 Список", "📊 Графики", "🗺️ Детали"])

            with tab1:
                # Отображение результатов списком
                for idx, row in results.iterrows():
                    with st.expander(
                        f"**{idx + 1}. {row['name']}** ⭐ {row.get('rating', 0):.1f} | "
                        f"Релевантность: {row['final_score']:.3f}",
                        expanded=(idx == 0)
                    ):
                        col1, col2 = st.columns([2, 1])

                        with col1:
                            st.markdown(f"**📍 Адрес:** {row.get('address', 'N/A')}")

                            if 'category' in row and pd.notna(row['category']):
                                st.markdown(f"**🏷️ Категория:** {row['category']}")

                            st.markdown(f"**💬 Релевантных отзывов:** {int(row['review_count'])}")

                        with col2:
                            if 'rating' in row and pd.notna(row['rating']):
                                st.metric("Рейтинг 2GIS", f"{row['rating']:.1f}/5.0")
                            st.metric("Релевантность", f"{row['final_score']:.3f}")

                        # Релевантные отзывы
                        st.markdown("#### 💬 Релевантные отзывы")

                        highlights = search_engine.get_place_highlights(
                            place_firm_id=row['place_firm_id'],
                            query=query,
                            top_k=3
                        )

                        if highlights:
                            for i, review in enumerate(highlights, 1):
                                st.info(f"**{i}.** {review}")
                        else:
                            st.warning("Отзывы не найдены")

            with tab2:
                # Визуализации
                if 'rating' in results.columns and 'final_score' in results.columns:
                    # График 1: Рейтинг vs Релевантность
                    fig1 = px.scatter(
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
                    st.plotly_chart(fig1, use_container_width=True)

                # График 2: Топ заведения
                fig2 = go.Figure(go.Bar(
                    x=results['final_score'],
                    y=[name[:40] for name in results['name']],
                    orientation='h',
                    text=results['final_score'].round(3),
                    textposition='auto',
                ))
                fig2.update_layout(
                    title=f'Топ-{len(results)} заведений по запросу',
                    xaxis_title='Релевантность',
                    yaxis_title='Заведение',
                    height=400 + len(results) * 20
                )
                st.plotly_chart(fig2, use_container_width=True)

                # График 3: Распределение по категориям
                if 'category' in results.columns:
                    category_counts = results['category'].value_counts().head(10)
                    fig3 = px.pie(
                        values=category_counts.values,
                        names=category_counts.index,
                        title='Распределение по категориям'
                    )
                    st.plotly_chart(fig3, use_container_width=True)

            with tab3:
                # Детальная таблица
                st.markdown("### 🗺️ Детальная информация")

                display_df = results.copy()

                # Форматирование колонок
                if 'rating' in display_df.columns:
                    display_df['rating'] = display_df['rating'].round(1)

                display_df['final_score'] = display_df['final_score'].round(3)
                display_df['avg_score'] = display_df['avg_score'].round(3)

                st.dataframe(
                    display_df,
                    use_container_width=True,
                    hide_index=True
                )

                # Кнопка экспорта
                csv = results.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Скачать результаты (CSV)",
                    data=csv,
                    file_name=f"search_results_{query[:30]}.csv",
                    mime="text/csv"
                )


# Футер
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: gray; font-size: 0.9em;'>
    <p>🚀 Powered by Semantic Search |
    📊 База данных: {total_reviews:,} отзывов, {total_places:,} заведений |
    🤖 Модель: {model_name}</p>
</div>
""".format(
    total_reviews=len(search_engine.reviews_df),
    total_places=len(search_engine.places_df),
    model_name=config.MODEL_NAME.split('/')[-1]
), unsafe_allow_html=True)
