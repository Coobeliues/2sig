"""
ПАРСЕР 2GIS - ФИНАЛЬНАЯ ВЕРСИЯ
Использует window.initialState для извлечения первых 50 отзывов
Все поля парсятся корректно: author, author_reviews_count, rating, text, date, is_verified
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import json
from typing import List
from dataclasses import dataclass, asdict
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class Review:
    author: str
    author_reviews_count: int
    rating: float
    text: str
    date: str
    is_verified: bool

@dataclass
class Place:
    name: str
    address: str
    category: str
    rating: float
    reviews_count: int
    phone: str
    url: str
    reviews: List[Review]

class TwoGISParser:
    """Парсер 2GIS с правильным извлечением всех полей"""

    def __init__(self, headless: bool = False):
        self.driver = self._init_driver(headless)
        self.wait = WebDriverWait(self.driver, 15)

    def _init_driver(self, headless: bool):
        options = Options()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        logger.info("✅ Chrome запущен")
        return driver

    def get_place_data(self, url: str) -> Place:
        """Получение данных через window.initialState"""
        logger.info(f"📄 Парсим: {url}")

        # Загружаем страницу с отзывами
        reviews_url = url.split('?')[0] + '/tab/reviews'
        self.driver.get(reviews_url)
        time.sleep(5)

        try:
            initial_state = self.driver.execute_script('return window.initialState')

            # Сохраняем для отладки
            with open('initial_state.json', 'w', encoding='utf-8') as f:
                json.dump(initial_state, f, ensure_ascii=False, indent=2)
            logger.info("💾 initialState сохранен в initial_state.json")

            # Извлекаем данные организации
            profile_data = initial_state.get('data', {}).get('entity', {}).get('profile', {})

            if not profile_data:
                logger.error("❌ Данные организации не найдены в initialState")
                return None

            # Берем первый объект
            org_data = list(profile_data.values())[0]['data']

            # Основные данные
            name = org_data.get('name', 'Неизвестно')
            address_obj = org_data.get('address', {})
            address = address_obj.get('name', 'Не указан')

            # Категория
            rubrics = org_data.get('rubrics', [])
            category = rubrics[0].get('name', 'Не указана') if rubrics else 'Не указана'

            # Рейтинг и отзывы
            reviews_obj = org_data.get('reviews', {})
            rating = reviews_obj.get('general_rating', 0.0)
            reviews_count = reviews_obj.get('general_review_count', 0)

            # Телефон
            phone = "Не указан"
            contact_groups = org_data.get('contact_groups', [])
            for group in contact_groups:
                contacts = group.get('contacts', [])
                for contact in contacts:
                    if contact.get('type') == 'phone':
                        phone = contact.get('text', phone)
                        break

            logger.info(f"✓ {name}")
            logger.info(f"  Рейтинг: {rating}, Отзывов: {reviews_count}")

            # Собираем отзывы
            reviews = self.get_reviews(initial_state)

            return Place(
                name=name,
                address=address,
                category=category,
                rating=rating,
                reviews_count=reviews_count,
                phone=phone,
                url=url,
                reviews=reviews
            )

        except Exception as e:
            logger.error(f"❌ Ошибка извлечения initialState: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_reviews(self, initial_state: dict) -> List[Review]:
        """Извлечение отзывов из initialState"""
        reviews = []

        try:
            # Ищем отзывы в initialState
            # Структура: initialState.data.review[id] = {data: {...}}
            reviews_data = initial_state.get('data', {}).get('review', {})

            if not reviews_data:
                logger.info("  ℹ️ Отзывы не найдены в initialState")
                return []

            logger.info(f"  🔍 Найдено {len(reviews_data)} отзывов в initialState")

            for review_id, review_obj in reviews_data.items():
                try:
                    review_data = review_obj.get('data', {})

                    # Извлекаем данные отзыва
                    text = review_data.get('text', '')
                    if len(text) < 30:
                        continue

                    rating = review_data.get('rating', 5.0)

                    # Дата: используем date_edited если есть (для отредактированных отзывов),
                    # иначе date_created (для новых отзывов)
                    date_edited = review_data.get('date_edited', '')
                    date_created = review_data.get('date_created', '')
                    date_str = date_edited if date_edited else date_created
                    date = date_str.split('T')[0] if 'T' in date_str else ''

                    # Данные пользователя
                    user = review_data.get('user', {})
                    author = user.get('name', 'Пользователь 2GIS')
                    author_reviews_count = user.get('reviews_count', 0)

                    # Статус модерации (is_hidden = True означает скрыт/на модерации)
                    is_hidden = review_data.get('is_hidden', False)
                    is_verified = not is_hidden  # Инвертируем: True = подтвержден, False = скрыт

                    reviews.append(Review(
                        author=author,
                        author_reviews_count=author_reviews_count,
                        rating=rating,
                        text=text[:500],
                        date=date,
                        is_verified=is_verified
                    ))

                except Exception as e:
                    logger.debug(f"Ошибка обработки отзыва {review_id}: {e}")
                    continue

            # Статистика по статусам
            verified_count = sum(1 for r in reviews if r.is_verified)
            unverified_count = len(reviews) - verified_count

            logger.info(f"  ✅ Извлечено {len(reviews)} отзывов (подтверждено: {verified_count}, на модерации: {unverified_count})")
            return reviews

        except Exception as e:
            logger.error(f"  ❌ Ошибка извлечения отзывов: {e}")
            import traceback
            traceback.print_exc()
            return []

    def save_to_json(self, places: List[Place], filename: str):
        """Сохранение в JSON"""
        data = [asdict(place) for place in places]

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"\n💾 Данные сохранены в {filename}")

    def close(self):
        """Закрытие браузера"""
        self.driver.quit()
        logger.info("👋 Готово!")

# ===================================================================
# ЗАПУСК
# ===================================================================
if __name__ == "__main__":
    import sys
    import io
    # Фикс кодировки для Windows
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 70)
    print("🚀 ПАРСЕР 2GIS - Финальная версия")
    print("=" * 70)
    print()

    scraper = TwoGISParser(headless=False)

    try:
        # Тестируем на одном URL
        url = "https://2gis.kz/almaty/firm/70000001057770550"

        place = scraper.get_place_data(url)

        if place:
            print("\n" + "=" * 70)
            print("📊 РЕЗУЛЬТАТЫ")
            print("=" * 70)
            print(f"\n{place.name}")
            print(f" 📍 {place.address}")
            print(f" 📂 {place.category}")
            print(f" ⭐ {place.rating} ({place.reviews_count} отзывов)")
            print(f" 📞 {place.phone}")
            print(f" 💬 Собрано отзывов: {len(place.reviews)}")

            if place.reviews:
                print(f"\n 📝 Примеры отзывов:")
                for j, review in enumerate(place.reviews[:10], 1):
                    count_str = f" ({review.author_reviews_count} отз.)" if review.author_reviews_count > 0 else ""
                    date_str = f" [{review.date}]" if review.date else ""
                    status_str = "" if review.is_verified else " [НЕ ПОДТВЕРЖДЕН]"
                    print(f" {j}. {review.author}{count_str} ⭐{review.rating}{date_str}{status_str}")
                    print(f"    \"{review.text[:80]}...\"")

            scraper.save_to_json([place], "2gis_result_final.json")

            print("\n" + "=" * 70)
            print("✅ ГОТОВО! Проверьте файл: 2gis_result_final.json")
            print("=" * 70)
        else:
            print("\n❌ Данные не собраны")

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

    finally:
        scraper.close()
