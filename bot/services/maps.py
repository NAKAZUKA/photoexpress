import os
from math import radians, sin, cos, sqrt, asin
from db.database import SessionLocal, PickupPoint

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")


def haversine(lat1, lon1, lat2, lon2):
    """Вычисляет расстояние в км между двумя точками (Haversine)."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 2 * 6371 * asin(sqrt(a))


def get_nearest_pickup_points(user_lat: float, user_lon: float, limit: int = 5):
    """Возвращает `limit` ближайших ПВЗ из БД."""
    db = SessionLocal()
    points = db.query(PickupPoint).all()
    db.close()
    # считаем расстояния и сортируем
    pts = [(p, haversine(user_lat, user_lon, float(p.lat), float(p.lon)))
           for p in points]
    pts_sorted = sorted(pts, key=lambda x: x[1])[:limit]
    return [p for p, _ in pts_sorted]


def generate_static_map_url(points: list[PickupPoint], size: str = "800x400") -> str:
    """
    Генерирует URL Google Static Map с маркерами.
    Метки нумеруются по порядку.
    """
    markers = []
    for idx, p in enumerate(points, start=1):
        markers.append(
            f"markers=color:red%7Clabel:{idx}%7C{p.lat},{p.lon}"
        )
    markers_param = "&".join(markers)
    return (
        "https://maps.googleapis.com/maps/api/staticmap"
        f"?size={size}&maptype=roadmap&{markers_param}"
        f"&key={GOOGLE_MAPS_API_KEY}"
    )
