
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import requests
import time
import json
import re
from typing import List, Dict
from dataclasses import dataclass, asdict
import logging
from datetime import datetime


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
    firm_id: str
    address: str
    category: str  # Категория из 2GIS (рубрика)
    category_search: str  # Категория поиска (кафе, ресторан и т.д.)
    rating: float
    reviews_count: int
    phone: str
    url: str
    reviews: List[Review]



class TwoGISMassParser:

    def __init__(self, headless: bool = True):
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

        # Отключаем изображения для ускорения
        prefs = {"profile.managed_default_content_settings.images": 2}
        options.add_experimental_option("prefs", prefs)

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        logger.info("✅ Chrome запущен")
        return driver

    def search_places(self, city: str, categories: List[str], max_per_category: int = 50) -> List[Dict]:
        all_places = []

        for category in categories:
            logger.info(f"\n🔍 Поиск заведений: {category} в {city}")

            # Формируем URL поиска
            search_url = f"https://2gis.kz/{city}/search/{category}"
            self.driver.get(search_url)
            time.sleep(5)

            # Скроллим чтобы загрузить больше результатов
            for i in range(5):  # 5 скроллов
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

            # Извлекаем ссылки на заведения
            try:
                # Ищем все ссылки на карточки заведений
                links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/firm/']")

                place_urls = set()
                for link in links:
                    href = link.get_attribute('href')
                    if href and '/firm/' in href:
                        # Извлекаем firm_id
                        match = re.search(r'/firm/(\d+)', href)
                        if match:
                            firm_id = match.group(1)
                            place_url = f"https://2gis.kz/{city}/firm/{firm_id}"
                            place_urls.add((firm_id, place_url))

                # Ограничиваем количество
                place_urls = list(place_urls)[:max_per_category]

                logger.info(f"  ✅ Найдено {len(place_urls)} заведений категории '{category}'")

                for firm_id, url in place_urls:
                    all_places.append({
                        'firm_id': firm_id,
                        'url': url,
                        'category_search': category
                    })

            except Exception as e:
                logger.error(f"  ❌ Ошибка поиска {category}: {e}")
                continue

        logger.info(f"\n📊 Всего найдено {len(all_places)} уникальных заведений")


        return all_places

    def get_firm_id_from_url(self, url: str) -> str:
        match = re.search(r'/firm/(\d+)', url)
        if match:
            return match.group(1)
        

        return None

    def get_all_reviews_via_api(self, firm_id: str) -> List[dict]:
        all_reviews = []
        offset = 0
        limit = 50

        api_url = f"https://public-api.reviews.2gis.com/3.0/branches/{firm_id}/reviews"

        while True:
            params = {
                'limit': limit,
                'offset': offset,
                'is_advertiser': 'false',
                'fields': 'meta.providers,meta.branch_rating,meta.branch_reviews_count,meta.total_count,reviews.hiding_reason,reviews.emojis',
                'without_my_first_review': 'false',
                'rated': 'true',
                'sort_by': 'date_created',
                'key': '6e7e1929-4ea9-4a5d-8c05-d601860389bd',
                'locale': 'ru_KZ'
            }

            try:
                response = self.session.get(api_url, params=params, timeout=30)

                if response.status_code != 200:
                    break

                data = response.json()
                items = data.get('reviews', [])

                if not items:
                    break

                all_reviews.extend(items)

                # Проверяем общее количество
                meta = data.get('meta', {})
                total_count = meta.get('total_count', 0)

                if len(all_reviews) >= total_count:
                    break

                offset += limit
                time.sleep(0.2)

            except Exception as e:
                logger.debug(f"Ошибка API: {e}")
                break


        return all_reviews

    def parse_reviews(self, reviews_data: List[dict]) -> List[Review]:
        reviews = []

        for review_data in reviews_data:
            try:
                text = review_data.get('text', '')
                if len(text) < 30:
                    continue

                rating = review_data.get('rating', 5.0)

                date_edited = review_data.get('date_edited', '')
                date_created = review_data.get('date_created', '')
                date_str = date_edited if date_edited else date_created
                date = date_str.split('T')[0] if 'T' in date_str else ''

                user = review_data.get('user', {})
                author = user.get('name', 'Пользователь 2GIS')
                author_reviews_count = user.get('reviews_count', 0)

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
                continue


        return reviews

    def get_place_data(self, place_info: Dict) -> Place:
        firm_id = place_info['firm_id']
        url = place_info['url']

        logger.info(f"  📄 Парсим: {firm_id}")

        # Загружаем страницу для получения базовой информации
        try:
            reviews_url = url.split('?')[0] + '/tab/reviews'
            self.driver.get(reviews_url)
            time.sleep(3)

            initial_state = self.driver.execute_script('return window.initialState')

            if not initial_state:
                return None

            profile_data = initial_state.get('data', {}).get('entity', {}).get('profile', {})

            if not profile_data:
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

            # Получаем отзывы через API
            reviews_data = self.get_all_reviews_via_api(firm_id)
            reviews = self.parse_reviews(reviews_data)

            logger.info(f"    ✓ {name}: собрано {len(reviews)} отзывов из {reviews_count}")

            return Place(
                name=name,
                firm_id=firm_id,
                address=address,
                category=category,
                category_search=place_info.get('category_search', ''),
                rating=rating,
                reviews_count=reviews_count,
                phone=phone,
                url=url,
                reviews=reviews
            )

        except Exception as e:
            logger.error(f"    ❌ Ошибка: {e}")

            return None

    def collect_mass_reviews(self, city: str, categories: List[str], max_per_category: int = 50) -> List[Place]:
        logger.info("=" * 70)
        logger.info("🚀 МАССОВЫЙ СБОР ОТЗЫВОВ 2GIS")
        logger.info("=" * 70)

        # Шаг 1: Поиск заведений
        places_info = self.search_places(city, categories, max_per_category)

        if not places_info:
            logger.error("❌ Заведения не найдены")
            return []

        # Шаг 2: Парсинг каждого заведения
        logger.info(f"\n📊 Начинаю парсинг {len(places_info)} заведений...")
        all_places = []

        for i, place_info in enumerate(places_info, 1):
            logger.info(f"\n[{i}/{len(places_info)}] Обрабатываю заведение...")

            place = self.get_place_data(place_info)

            if place and len(place.reviews) > 0:
                all_places.append(place)

            # Небольшая пауза между запросами
            time.sleep(1)

        logger.info(f"\n✅ Собрано {len(all_places)} заведений с отзывами")

        # Статистика 
        total_reviews = sum(len(p.reviews) for p in all_places) 
        logger.info(f"📊 Всего отзывов: {total_reviews}")


        return all_places

    def save_to_json(self, places: List[Place], filename: str):
        data = [asdict(place) for place in places]

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"\n💾 Данные сохранены в {filename}")

    def close(self):
        self.driver.quit()

# ==================================================================
# ЗАПУСК   
# ===================================================================
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


    # Настройки сбора
    CITY = "almaty"  # Город для поиска

    # Категории заведений для сбора
    CATEGORIES = [
        "кафе",
        "ресторан",
        "бар",
        "кофейня",
        "пиццерия",
        "суши",
        "фастфуд",
        "бургерная",
        "кондитерская",
        "пекарня"
    ]

    MAX_PER_CATEGORY = 10  # Максимум заведений на категорию (всего будет ~100 заведений)

    OUTPUT_FILE = f"2gis_mass_reviews_{CITY}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    print("=" * 70)
    print("🚀 МАССОВЫЙ СБОР ОТЗЫВОВ 2GIS")
    print("=" * 70)
    print(f"\n📍 Город: {CITY}")
    print(f"📂 Категории: {', '.join(CATEGORIES)}")
    print(f"🔢 Макс. на категорию: {MAX_PER_CATEGORY}")
    print(f"📁 Файл результата: {OUTPUT_FILE}")
    print("\n" + "=" * 70 + "\n")

    scraper = TwoGISMassParser(headless=False)

    try:
        # Собираем данные
        places = scraper.collect_mass_reviews(CITY, CATEGORIES, MAX_PER_CATEGORY)

        if places:
            # Сохраняем
            scraper.save_to_json(places, OUTPUT_FILE)

            # Итоговая статистика
            print("\n" + "=" * 70)
            print("📊 ИТОГОВАЯ СТАТИСТИКА")
            print("=" * 70)

            total_reviews = sum(len(p.reviews) for p in places)
            total_places = len(places)

            print(f"\n✅ Заведений обработано: {total_places}")
            print(f"✅ Всего отзывов собрано: {total_reviews}")
            print(f"📈 Средне отзывов на заведение: {total_reviews / total_places:.1f}")

            # Топ-5 заведений по количеству отзывов
            top_places = sorted(places, key=lambda p: len(p.reviews), reverse=True)[:5]
            print(f"\n🏆 Топ-5 заведений по количеству отзывов:")
            for i, place in enumerate(top_places, 1):
                print(f"  {i}. {place.name}: {len(place.reviews)} отзывов")

            print("\n" + "=" * 70)
            print(f"✅ ГОТОВО! Результаты сохранены в: {OUTPUT_FILE}")
            print("=" * 70)
        else:
            print("\n❌ Данные не собраны")

    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    finally:
        scraper.close()
        logger.info("👋 Завершено!")

    

 
 
