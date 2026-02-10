"""
ПАРСЕР 2GIS v2 FINAL
Парсит отзывы из DOM после загрузки всех через "Показать ещё"
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
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

class TwoGISParserV2Final:
    """Финальная версия парсера - парсит отзывы из DOM"""

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

    def load_all_reviews(self, url: str):
        """Загружает ВСЕ отзывы кликая на 'Показать ещё'"""
        logger.info(f"📄 Загружаю все отзывы с: {url}")

        self.driver.get(url)
        time.sleep(5)

        # Переходим на вкладку отзывов
        reviews_url = url.split('?')[0] + '/tab/reviews'
        logger.info(f"  ➡️ Переход на вкладку отзывов...")
        self.driver.get(reviews_url)
        time.sleep(5)

        # Кликаем на "Показать ещё" пока можем
        logger.info(f"  📜 Загружаю все отзывы (клик)...")
        click_count = 0
        max_clicks = 300

        while click_count < max_clicks:
            # Скроллим вниз
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.8)

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

                    if click_count % 20 == 0:
                        articles_count = len(self.driver.find_elements(By.TAG_NAME, "article"))
                        logger.info(f"    Клик #{click_count}: отображается {articles_count} отзывов")

                    time.sleep(0.8)
                else:
                    # Кнопка не найдена - все загружены
                    articles_count = len(self.driver.find_elements(By.TAG_NAME, "article"))
                    logger.info(f"  ✅ Кнопка 'Показать ещё' не найдена!")
                    logger.info(f"  💾 Всего отображается {articles_count} отзывов")
                    break

            except Exception as e:
                logger.debug(f"    Ошибка: {e}")
                break

        logger.info(f"  ⏱️ Ждем 3 секунды для полной загрузки...")
        time.sleep(3)

    def parse_reviews_from_dom(self) -> List[Review]:
        """Парсит отзывы из DOM"""
        reviews = []

        # Находим все элементы article
        articles = self.driver.find_elements(By.TAG_NAME, "article")
        logger.info(f"  🔍 Найдено {len(articles)} article элементов")

        for i, article in enumerate(articles):
            try:
                # Извлекаем текст отзыва
                text_element = article.find_element(By.CSS_SELECTOR, "[itemprop='reviewBody'], [class*='text'], [class*='Text']")
                text = text_element.text.strip()

                if len(text) < 10:
                    continue

                # Извлекаем рейтинг (из meta тега или aria-label)
                try:
                    rating_el = article.find_element(By.CSS_SELECTOR, "[itemprop='ratingValue'], [aria-label*='звезд']")
                    rating_text = rating_el.get_attribute('content') or rating_el.get_attribute('aria-label')

                    if rating_text:
                        # Извлекаем число из текста
                        rating_match = re.search(r'(\d+)', rating_text)
                        rating = float(rating_match.group(1)) if rating_match else 5.0
                    else:
                        rating = 5.0
                except:
                    rating = 5.0

                # Извлекаем автора
                try:
                    author_el = article.find_element(By.CSS_SELECTOR, "[itemprop='author'], [class*='author'], [class*='Author'], [class*='name']")
                    author = author_el.text.strip()
                except:
                    author = "Пользователь 2GIS"

                # Извлекаем количество отзывов автора
                author_reviews_count = 0
                try:
                    # Ищем текст вида "42 отзыва" или "(42)"
                    author_info = article.text
                    count_match = re.search(r'(\d+)\s*отз', author_info, re.IGNORECASE)
                    if count_match:
                        author_reviews_count = int(count_match.group(1))
                    else:
                        count_match = re.search(r'\((\d+)\)', author_info)
                        if count_match:
                            author_reviews_count = int(count_match.group(1))
                except:
                    pass

                # Извлекаем дату
                date = ""
                try:
                    date_el = article.find_element(By.CSS_SELECTOR, "[itemprop='datePublished'], [datetime], [class*='date'], [class*='Date']")
                    date_text = date_el.get_attribute('content') or date_el.get_attribute('datetime') or date_el.text
                    if date_text:
                        # Парсим дату (может быть ISO формат или обычный текст)
                        date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_text)
                        if date_match:
                            date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                except:
                    pass

                # Статус верификации (предполагаем что все видимые - подтвержденные)
                is_verified = True

                reviews.append(Review(
                    author=author,
                    author_reviews_count=author_reviews_count,
                    rating=rating,
                    text=text[:500],
                    date=date,
                    is_verified=is_verified
                ))

            except Exception as e:
                logger.debug(f"Ошибка парсинга article #{i}: {e}")
                continue

        logger.info(f"  ✅ Спарсено {len(reviews)} отзывов из DOM")
        return reviews

    def get_place_data(self, url: str) -> Place:
        """Получение данных места"""
        logger.info(f"📄 Парсим: {url}")

        # Сначала загружаем ВСЕ отзывы
        self.load_all_reviews(url)

        # Получаем основные данные из initialState
        try:
            initial_state = self.driver.execute_script('return window.initialState')

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
            logger.info(f"  Рейтинг: {rating}, Отзывов: {reviews_count}")

            # Парсим отзывы из DOM
            reviews = self.parse_reviews_from_dom()

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
    print("🚀 ПАРСЕР 2GIS v2 FINAL - Парсинг из DOM")
    print("=" * 70)
    print()

    scraper = TwoGISParserV2Final(headless=False)

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
                for j, review in enumerate(place.reviews[:5], 1):
                    count_str = f" ({review.author_reviews_count} отз.)" if review.author_reviews_count > 0 else ""
                    date_str = f" [{review.date}]" if review.date else ""
                    status_str = "" if review.is_verified else " [НЕ ПОДТВЕРЖДЕН]"
                    print(f" {j}. {review.author}{count_str} ⭐{review.rating}{date_str}{status_str}")
                    print(f"    \"{review.text[:80]}...\"")

            scraper.save_to_json([place], "2gis_result_v2_final.json")

            print("\n" + "=" * 70)
            print("✅ ГОТОВО! Проверьте файл: 2gis_result_v2_final.json")
            print("=" * 70)
        else:
            print("\n❌ Данные не собраны")

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

    finally:
        scraper.close()
