"""
ПАРСЕР 2GIS v3 - Прямые API запросы
Использует официальное API 2GIS для получения всех отзывов
"""
import requests
import json
from typing import List
from dataclasses import dataclass, asdict
import logging
import time

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

class TwoGISParserV3:
    """Парсер использующий прямые API запросы"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        })

    def get_firm_id_from_url(self, url: str) -> str:
        """Извлекает ID фирмы из URL"""
        # URL вида: https://2gis.kz/almaty/firm/70000001057770550
        parts = url.rstrip('/').split('/')
        return parts[-1]

    def get_place_info(self, firm_id: str) -> dict:
        """Получает информацию о месте через API"""
        api_url = f"https://public-api.reviews.2gis.com/2.0/branches/{firm_id}/reviews"

        params = {
            'limit': 50,
            'offset': 0,
            'sort_by': 'date_created',
            'key': 'rucrcu1809',  # Публичный ключ API 2GIS
            'fields': 'meta.providers,meta.branch,meta.branch_rating,items.id,items.text,items.rating,items.date_created,items.date_edited,items.user,items.is_hidden'
        }

        try:
            response = self.session.get(api_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data
        except Exception as e:
            logger.error(f"❌ Ошибка API запроса: {e}")
            logger.debug(f"URL: {response.url if 'response' in locals() else api_url}")
            return None

    def get_all_reviews(self, firm_id: str) -> List[dict]:
        """Получает ВСЕ отзывы через API с пагинацией"""
        all_reviews = []
        offset = 0
        limit = 50

        api_url = f"https://public-api.reviews.2gis.com/2.0/branches/{firm_id}/reviews"

        params = {
            'limit': limit,
            'sort_by': 'date_created',
            'key': 'rucrcu1809',
            'fields': 'items.id,items.text,items.rating,items.date_created,items.date_edited,items.user,items.is_hidden'
        }

        logger.info(f"  📜 Загружаю отзывы через API...")

        while True:
            params['offset'] = offset

            try:
                response = self.session.get(api_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                items = data.get('items', [])
                if not items:
                    break

                all_reviews.extend(items)
                logger.info(f"    Загружено {len(all_reviews)} отзывов...")

                # Проверяем есть ли еще отзывы
                meta = data.get('meta', {})
                total_count = meta.get('total_count', 0)

                if len(all_reviews) >= total_count:
                    break

                offset += limit
                time.sleep(0.5)  # Небольшая задержка между запросами

            except Exception as e:
                logger.error(f"❌ Ошибка при загрузке отзывов (offset={offset}): {e}")
                break

        logger.info(f"  ✅ Всего загружено {len(all_reviews)} отзывов")
        return all_reviews

    def parse_place(self, url: str) -> Place:
        """Парсинг места по URL"""
        logger.info(f"📄 Парсим: {url}")

        firm_id = self.get_firm_id_from_url(url)
        logger.info(f"  🆔 Firm ID: {firm_id}")

        # Получаем информацию о месте
        place_data = self.get_place_info(firm_id)

        if not place_data:
            return None

        # Извлекаем метаданные
        meta = place_data.get('meta', {})
        branch = meta.get('branch', {})
        branch_rating = meta.get('branch_rating', {})

        name = branch.get('name', 'Неизвестно')
        address = branch.get('address', 'Не указан')
        category = branch.get('rubrics', [{}])[0].get('name', 'Не указана') if branch.get('rubrics') else 'Не указана'

        rating = branch_rating.get('general_rating', 0.0)
        reviews_count = branch_rating.get('general_review_count', 0)

        # Телефон
        phone = "Не указан"
        contact_groups = branch.get('contact_groups', [])
        for group in contact_groups:
            contacts = group.get('contacts', [])
            for contact in contacts:
                if contact.get('type') == 'phone':
                    phone = contact.get('text', phone)
                    break

        logger.info(f"✓ {name}")
        logger.info(f"  Рейтинг: {rating}, Отзывов: {reviews_count}")

        # Получаем ВСЕ отзывы
        all_reviews_raw = self.get_all_reviews(firm_id)

        # Парсим отзывы
        reviews = []
        for review_data in all_reviews_raw:
            try:
                text = review_data.get('text', '')
                if len(text) < 30:
                    continue

                rating_val = review_data.get('rating', 5.0)

                # Дата
                date_edited = review_data.get('date_edited', '')
                date_created = review_data.get('date_created', '')
                date_str = date_edited if date_edited else date_created
                date = date_str.split('T')[0] if 'T' in date_str else ''

                # Пользователь
                user = review_data.get('user', {})
                author = user.get('name', 'Пользователь 2GIS')
                author_reviews_count = user.get('reviews_count', 0)

                # Статус
                is_hidden = review_data.get('is_hidden', False)
                is_verified = not is_hidden

                reviews.append(Review(
                    author=author,
                    author_reviews_count=author_reviews_count,
                    rating=rating_val,
                    text=text[:500],
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

    def save_to_json(self, places: List[Place], filename: str):
        """Сохранение в JSON"""
        data = [asdict(place) for place in places]

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"\n💾 Данные сохранены в {filename}")

# ===================================================================
# ЗАПУСК
# ===================================================================
if __name__ == "__main__":
    import sys
    import io
    # Фикс кодировки для Windows
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 70)
    print("🚀 ПАРСЕР 2GIS v3 - Прямые API запросы")
    print("=" * 70)
    print()

    parser = TwoGISParserV3()

    try:
        # Тестируем на одном URL
        url = "https://2gis.kz/almaty/firm/70000001057770550"

        place = parser.parse_place(url)

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

            parser.save_to_json([place], "2gis_result_v3.json")

            print("\n" + "=" * 70)
            print("✅ ГОТОВО! Проверьте файл: 2gis_result_v3.json")
            print("=" * 70)
        else:
            print("\n❌ Данные не собраны")

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
