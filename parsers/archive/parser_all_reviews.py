"""
ПАРСЕР 2GIS - ВСЕ ОТЗЫВЫ
Использует selenium-wire для перехвата API запросов
Позволяет получить ВСЕ отзывы, а не только первые 50
"""
from seleniumwire import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import json
from typing import List, Dict
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

class TwoGISParserAllReviews:
    """Парсер с перехватом API для получения ВСЕХ отзывов"""

    def __init__(self, headless: bool = False):
        self.all_reviews = {}  # Словарь для хранения всех уникальных отзывов
        self.driver = self._init_driver(headless)

    def _init_driver(self, headless: bool):
        options = Options()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')

        # Отключаем изображения для ускорения
        prefs = {"profile.managed_default_content_settings.images": 2}
        options.add_experimental_option("prefs", prefs)

        service = Service(ChromeDriverManager().install())

        # Используем selenium-wire для перехвата запросов
        seleniumwire_options = {
            'disable_encoding': True  # Для декодирования ответов
        }

        driver = webdriver.Chrome(
            service=service,
            options=options,
            seleniumwire_options=seleniumwire_options
        )

        logger.info("✅ Chrome запущен с перехватом сети")
        return driver

    def _process_network_requests(self):
        """Обрабатывает сетевые запросы и извлекает отзывы из API ответов"""
        for request in self.driver.requests:
            # Ищем запросы к API с отзывами
            if request.response and 'reviews' in request.url:
                try:
                    # Декодируем тело ответа
                    body = request.response.body.decode('utf-8')
                    data = json.loads(body)

                    # Ищем отзывы в разных возможных структурах
                    items = None
                    if 'items' in data:
                        items = data['items']
                    elif 'result' in data and isinstance(data['result'], dict) and 'items' in data['result']:
                        items = data['result']['items']
                    elif 'data' in data and 'review' in data['data']:
                        items = data['data']['review'].values()

                    if items:
                        for item in items:
                            # Извлекаем ID отзыва
                            if isinstance(item, dict):
                                review_id = item.get('id') or item.get('local_item_id')
                                if review_id and review_id not in self.all_reviews:
                                    self.all_reviews[review_id] = item

                except Exception as e:
                    logger.debug(f"Ошибка обработки запроса {request.url}: {e}")
                    continue

    def load_all_reviews(self, url: str):
        """Загружает ВСЕ отзывы через скроллинг и клики"""
        logger.info(f"📄 Загружаю все отзывы с: {url}")

        # Сначала загружаем основную страницу
        self.driver.get(url)
        time.sleep(5)

        # Переходим на вкладку отзывов
        reviews_url = url.split('?')[0] + '/tab/reviews'
        logger.info(f"  ➡️ Переход на вкладку отзывов...")
        self.driver.get(reviews_url)
        time.sleep(8)  # Увеличили ожидание

        logger.info(f"  📜 Загружаю все отзывы (клик + перехват API)...")
        click_count = 0
        max_clicks = 300
        last_count = 0
        no_change_count = 0

        while click_count < max_clicks:
            # Скроллим вниз
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)

            # Обрабатываем сетевые запросы
            self._process_network_requests()

            # Ищем кнопку "Показать ещё"
            try:
                button = self.driver.execute_script("""
                    const buttons = document.querySelectorAll('button, div[role="button"], a');
                    for (let btn of buttons) {
                        if (btn.textContent.includes('Показать') ||
                            btn.textContent.includes('ещё') ||
                            btn.textContent.includes('еще')) {
                            return btn;
                        }
                    }
                    return null;
                """)

                if button:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                    time.sleep(0.3)
                    self.driver.execute_script("arguments[0].click();", button)
                    click_count += 1

                    # Проверяем прогресс
                    current_count = len(self.all_reviews)

                    if click_count % 20 == 0:
                        logger.info(f"    Клик #{click_count}: собрано {current_count} уникальных отзывов")

                    # Если количество не меняется - возможно все загружены
                    if current_count == last_count:
                        no_change_count += 1
                        if no_change_count >= 10:
                            logger.info(f"  ✅ Количество отзывов не меняется - все загружены!")
                            break
                    else:
                        no_change_count = 0

                    last_count = current_count
                    time.sleep(0.5)
                else:
                    # Кнопка не найдена
                    logger.info(f"  ✅ Кнопка 'Показать ещё' не найдена!")
                    break

            except Exception as e:
                logger.debug(f"    Ошибка: {e}")
                break

        # Финальная обработка всех запросов
        self._process_network_requests()
        logger.info(f"  💾 Всего собрано {len(self.all_reviews)} уникальных отзывов")

    def parse_reviews(self) -> List[Review]:
        """Парсит собранные отзывы"""
        reviews = []

        logger.info(f"  🔍 Обрабатываю {len(self.all_reviews)} отзывов...")

        for review_id, review_data in self.all_reviews.items():
            try:
                # Обрабатываем разные структуры данных
                if 'data' in review_data:
                    review_data = review_data['data']

                # Текст отзыва
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
                    text=text[:500],
                    date=date,
                    is_verified=is_verified
                ))

            except Exception as e:
                logger.debug(f"Ошибка обработки отзыва {review_id}: {e}")
                continue

        # Статистика
        verified_count = sum(1 for r in reviews if r.is_verified)
        unverified_count = len(reviews) - verified_count

        logger.info(f"  ✅ Извлечено {len(reviews)} отзывов (подтверждено: {verified_count}, на модерации: {unverified_count})")
        return reviews

    def get_place_data(self, url: str) -> Place:
        """Получение данных места"""
        logger.info(f"📄 Парсим: {url}")

        # Загружаем все отзывы
        self.load_all_reviews(url)

        # Получаем базовую информацию из initialState
        try:
            initial_state = self.driver.execute_script('return window.initialState')

            if not initial_state:
                logger.error("❌ window.initialState пустой или не найден")
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

            # Парсим собранные отзывы
            reviews = self.parse_reviews()

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
    print("🚀 ПАРСЕР 2GIS - ВСЕ ОТЗЫВЫ (с перехватом API)")
    print("=" * 70)
    print()

    scraper = TwoGISParserAllReviews(headless=False)

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

            scraper.save_to_json([place], "2gis_all_reviews.json")

            print("\n" + "=" * 70)
            print(f"✅ ГОТОВО! Собрано {len(place.reviews)} отзывов из {place.reviews_count}")
            print("✅ Проверьте файл: 2gis_all_reviews.json")
            print("=" * 70)
        else:
            print("\n❌ Данные не собраны")

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

    finally:
        scraper.close()
