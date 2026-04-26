import re
from typing import Any
from urllib.parse import parse_qs, urlparse


_DMS_PATTERN = re.compile(
    r"(\d{1,3})[^\dNSWE]+(\d{1,2})[^\dNSWE]+(\d{1,2}(?:\.\d+)?)[^\dNSWE]*([NS])"
    r"(?:\s|,|;)+"
    r"(\d{1,3})[^\dNSWE]+(\d{1,2})[^\dNSWE]+(\d{1,2}(?:\.\d+)?)[^\dNSWE]*([EW])",
    re.IGNORECASE,
)
_DECIMAL_PAIR_PATTERN = re.compile(
    r"(-?\d{1,3}(?:\.\d+)?)\s*[,;/]\s*(-?\d{1,3}(?:\.\d+)?)"
)
_GOOGLE_AT_PATTERN = re.compile(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")
_OPENSTREETMAP_HASH_PATTERN = re.compile(r"map=\d+\/(-?\d+(?:\.\d+)?)\/(-?\d+(?:\.\d+)?)")


def _format_coordinate(value: float) -> str:
    normalized = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if normalized in {"", "-0"} else normalized


def build_google_maps_url(latitude: float | str, longitude: float | str) -> str:
    lat = _format_coordinate(float(latitude))
    lng = _format_coordinate(float(longitude))
    return f"https://www.google.com/maps?q={lat},{lng}"


def _is_valid_coordinate_pair(latitude: float, longitude: float) -> bool:
    return -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0


def _parse_decimal_pair(raw_value: str) -> tuple[str, str] | None:
    direct_match = _DECIMAL_PAIR_PATTERN.search(raw_value)
    if direct_match:
        latitude = float(direct_match.group(1))
        longitude = float(direct_match.group(2))
        if _is_valid_coordinate_pair(latitude, longitude):
            return _format_coordinate(latitude), _format_coordinate(longitude)

    numeric_matches = re.findall(r"-?\d+(?:\.\d+)?", raw_value)
    if len(numeric_matches) != 2:
        return None

    latitude = float(numeric_matches[0])
    longitude = float(numeric_matches[1])
    if not _is_valid_coordinate_pair(latitude, longitude):
        return None

    return _format_coordinate(latitude), _format_coordinate(longitude)


def _parse_dms_pair(raw_value: str) -> tuple[str, str] | None:
    match = _DMS_PATTERN.search(raw_value)
    if not match:
        return None

    lat_deg, lat_min, lat_sec, lat_dir, lon_deg, lon_min, lon_sec, lon_dir = match.groups()
    latitude = float(lat_deg) + float(lat_min) / 60 + float(lat_sec) / 3600
    longitude = float(lon_deg) + float(lon_min) / 60 + float(lon_sec) / 3600

    if lat_dir.upper() == "S":
        latitude = -latitude
    if lon_dir.upper() == "W":
        longitude = -longitude

    if not _is_valid_coordinate_pair(latitude, longitude):
        return None

    return _format_coordinate(latitude), _format_coordinate(longitude)


def _extract_google_coordinates(parsed_url, raw_value: str) -> tuple[str, str] | None:
    for key in ("q", "query", "ll", "center", "destination"):
        for candidate in parse_qs(parsed_url.query).get(key, []):
            parsed_pair = extract_coordinates(candidate)
            if parsed_pair:
                return parsed_pair

    marker_match = _GOOGLE_AT_PATTERN.search(raw_value)
    if marker_match:
        latitude = float(marker_match.group(1))
        longitude = float(marker_match.group(2))
        if _is_valid_coordinate_pair(latitude, longitude):
            return _format_coordinate(latitude), _format_coordinate(longitude)

    return None


def _extract_openstreetmap_coordinates(parsed_url) -> tuple[str, str] | None:
    query = parse_qs(parsed_url.query)

    marker_values = query.get("marker", [])
    for marker_value in marker_values:
        parsed_pair = _parse_decimal_pair(marker_value)
        if parsed_pair:
            return parsed_pair

    lat_values = query.get("mlat", [])
    lng_values = query.get("mlon", [])
    if lat_values and lng_values:
        parsed_pair = _parse_decimal_pair(f"{lat_values[0]},{lng_values[0]}")
        if parsed_pair:
            return parsed_pair

    hash_match = _OPENSTREETMAP_HASH_PATTERN.search(parsed_url.fragment or "")
    if hash_match:
        latitude = float(hash_match.group(1))
        longitude = float(hash_match.group(2))
        if _is_valid_coordinate_pair(latitude, longitude):
            return _format_coordinate(latitude), _format_coordinate(longitude)

    return None


def extract_coordinates(raw_value: Any) -> tuple[str, str] | None:
    text = str(raw_value or "").strip()
    if not text:
        return None

    dms_pair = _parse_dms_pair(text)
    if dms_pair:
        return dms_pair

    try:
        parsed_url = urlparse(text)
    except ValueError:
        parsed_url = None

    if parsed_url and parsed_url.scheme and parsed_url.netloc:
        hostname = parsed_url.netloc.lower()

        if "google." in hostname or "goo.gl" in hostname:
            google_pair = _extract_google_coordinates(parsed_url, text)
            if google_pair:
                return google_pair

        if "openstreetmap." in hostname:
            osm_pair = _extract_openstreetmap_coordinates(parsed_url)
            if osm_pair:
                return osm_pair

    return _parse_decimal_pair(text)


def normalize_contact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)

    latitude = normalized.get("latitude")
    longitude = normalized.get("longitude")
    map_url = normalized.get("map_url")

    parsed_pair: tuple[str, str] | None = None
    if latitude not in {None, ""} and longitude not in {None, ""}:
        parsed_pair = extract_coordinates(f"{latitude},{longitude}")

    if parsed_pair is None and map_url not in {None, ""}:
        parsed_pair = extract_coordinates(map_url)

    if parsed_pair:
        normalized["latitude"], normalized["longitude"] = parsed_pair
        normalized["map_url"] = build_google_maps_url(*parsed_pair)
    elif map_url is not None:
        stripped_map_url = str(map_url).strip()
        normalized["map_url"] = stripped_map_url or None

    return normalized
