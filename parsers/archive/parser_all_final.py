"""
ПАРСЕР 2GIS - ВСЕ ОТЗЫВЫ (ФИНАЛЬНАЯ РАБОЧАЯ ВЕРСИЯ)
Использует Selenium для получения базовой информации
И прямые API запросы для получения ВСЕХ отзывов
"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import requests
import time
import json
import re
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

class TwoGISParserAllFinal:
    """Парсер с Selenium + прямые API запросы"""

    def __init__(self, headless: bool = False):
        self.driver = self._init_driver(headless)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        })

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

    def get_firm_id_from_url(self, url: str) -> str:
        """Извлекает ID фирмы из URL"""
        # URL вида: https://2gis.kz/almaty/firm/70000001057770550
        match = re.search(r'/firm/(\d+)', url)
        if match:
            return match.group(1)
        return None

    def get_all_reviews_via_api(self, firm_id: str, region_id: int = 12) -> List[dict]:
        """Получает ВСЕ отзывы через внутренний API 2GIS"""
        all_reviews = []
        offset = 0
        limit = 50

        # URL внутреннего API 2GIS v3.0 (используется на их сайте)
        api_url = f"https://public-api.reviews.2gis.com/3.0/branches/{firm_id}/reviews"

        logger.info(f"  📜 Загружаю отзывы через API 2GIS v3.0...")

        while True:
            params = {
                'limit': limit,
                'offset': offset,
                'is_advertiser': 'false',
                'fields': 'meta.providers,meta.branch_rating,meta.branch_reviews_count,meta.total_count,reviews.hiding_reason,reviews.emojis',
                'without_my_first_review': 'false',
                'rated': 'true',
                'sort_by': 'date_created',
                'key': '6e7e1929-4ea9-4a5d-8c05-d601860389bd',  # Публичный ключ из браузера
                'locale': 'ru_KZ'
            }

            try:
                response = self.session.get(api_url, params=params, timeout=30)

                if response.status_code != 200:
                    logger.warning(f"  ⚠️ API вернул статус {response.status_code}")
                    logger.debug(f"  URL: {response.url}")
                    logger.debug(f"  Response: {response.text[:500]}")
                    break

                data = response.json()
                # API v3.0 возвращает 'reviews' вместо 'items'
                items = data.get('reviews', [])

                if not items:
                    break

                all_reviews.extend(items)

                # Проверяем общее количество
                meta = data.get('meta', {})
                total_count = meta.get('total_count', 0)

                if offset % 200 == 0:
                    logger.info(f"    Загружено {len(all_reviews)} из {total_count} отзывов...")

                if len(all_reviews) >= total_count:
                    break

                offset += limit
                time.sleep(0.3)  # Небольшая задержка

            except Exception as e:
                logger.error(f"  ❌ Ошибка API запроса (offset={offset}): {e}")
                break

        logger.info(f"  ✅ Всего загружено {len(all_reviews)} отзывов через API")
        return all_reviews

    def parse_reviews(self, reviews_data: List[dict]) -> List[Review]:
        """Парсит отзывы из API данных"""
        reviews = []

        for review_data in reviews_data:
            try:
                # Текст
                text = review_data.get('text', '')
                if len(text) < 30:
                    continue

                # Рейтинг
                rating = review_data.get('rating', 5.0)

                # Дата
                date_edited = review_data.get('date_edited', '')
                date_created = review_data.get('date_created', '')
                date_str = date_edited if date_edited else date_created
                date = date_str.split('T')[0] if 'T' in date_str else ''

                # Автор
                user = review_data.get('user', {})
                author = user.get('name', 'Пользователь 2GIS')
                author_reviews_count = user.get('reviews_count', 0)

                # Статус
                is_hidden = review_data.get('is_hidden', False)
                is_verified = not is_hidden

                reviews.append(Review(
                    author=author,
                    author_reviews_count=author_reviews_count,
                    rating=rating,
                    text=text,  # БЕЗ ЛИМИТА - весь текст
                    date=date,
                    is_verified=is_verified
                ))

            except Exception as e:
                logger.debug(f"Ошибка обработки отзыва: {e}")
                continue

        # Статистика
        verified_count = sum(1 for r in reviews if r.is_verified)
        unverified_count = len(reviews) - verified_count

        logger.info(f"  ✅ Извлечено {len(reviews)} отзывов (подтверждено: {verified_count}, на модерации: {unverified_count})")
        return reviews

    def get_place_data(self, url: str) -> Place:
        """Получение данных места"""
        logger.info(f"📄 Парсим: {url}")

        # Получаем ID фирмы
        firm_id = self.get_firm_id_from_url(url)
        if not firm_id:
            logger.error("❌ Не удалось извлечь ID фирмы из URL")
            return None

        logger.info(f"  🆔 Firm ID: {firm_id}")

        # Загружаем страницу для получения базовой информации
        reviews_url = url.split('?')[0] + '/tab/reviews'
        self.driver.get(reviews_url)
        time.sleep(5)

        # Получаем базовую информацию из initialState
        try:
            initial_state = self.driver.execute_script('return window.initialState')

            if not initial_state:
                logger.error("❌ window.initialState не найден")
                return None

            profile_data = initial_state.get('data', {}).get('entity', {}).get('profile', {})

            if not profile_data:
                logger.error("❌ Данные организации не найдены")
                return None

            org_data = list(profile_data.values())[0]['data']

            name = org_data.get('name', 'Неизвестно')
            address_obj = org_data.get('address', {})
            address = address_obj.get('name', 'Не указан')

            rubrics = org_data.get('rubrics', [])
            category = rubrics[0].get('name', 'Не указана') if rubrics else 'Не указана'

            reviews_obj = org_data.get('reviews', {})
            rating = reviews_obj.get('general_rating', 0.0)
            reviews_count = reviews_obj.get('general_review_count', 0)

            phone = "Не указан"
            contact_groups = org_data.get('contact_groups', [])
            for group in contact_groups:
                contacts = group.get('contacts', [])
                for contact in contacts:
                    if contact.get('type') == 'phone':
                        phone = contact.get('text', phone)
                        break

            logger.info(f"✓ {name}")
            logger.info(f"  Рейтинг: {rating}, Отзывов всего: {reviews_count}")

            # Получаем ВСЕ отзывы через API
            reviews_data = self.get_all_reviews_via_api(firm_id)

            # Парсим отзывы
            reviews = self.parse_reviews(reviews_data)

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
            logger.error(f"❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
            return None

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
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 70)
    print("🚀 ПАРСЕР 2GIS - ВСЕ ОТЗЫВЫ (Selenium + API)")
    print("=" * 70)
    print()

    scraper = TwoGISParserAllFinal(headless=False)

    try:
        url = "https://2gis.kz/almaty/firm/70000001057770550"

        place = scraper.get_place_data(url)

        if place:
            print("\n" + "=" * 70)
            print("📊 РЕЗУЛЬТАТЫ")
            print("=" * 70)
            print(f"\n{place.name}")
            print(f" 📍 {place.address}")
            print(f" 📂 {place.category}")
            print(f" ⭐ {place.rating} (всего {place.reviews_count} отзывов)")
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

            scraper.save_to_json([place], "2gis_all_reviews_final.json")

            print("\n" + "=" * 70)
            print(f"✅ ГОТОВО! Собрано {len(place.reviews)} отзывов из {place.reviews_count}")
            print(f"✅ Процент покрытия: {len(place.reviews) / place.reviews_count * 100:.1f}%")
            print("✅ Проверьте файл: 2gis_all_reviews_final.json")
            print("=" * 70)
        else:
            print("\n❌ Данные не собраны")

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

    finally:
        scraper.close()
