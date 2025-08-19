import argparse
import requests
import json
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse
import os
import re
from dotenv import load_dotenv


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="""Консольная утилита для конвертации закладок Яндекс Карт в GPX."""
    )
    parser.add_argument("url", type=str, help="""URL для получения данных.""")
    parser.add_argument(
        "output_dir", type=str, help="""Путь к папке для сохранения GPX файла."""
    )
    parser.add_argument(
        "--api_key",
        type=str,
        help="""API ключ для Яндекс Геокодера. Если не указан, будет использована переменная окружения YANDEX_GEOCODER_API_KEY.""",
    )
    args = parser.parse_args()

    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-GB,en;q=0.9",
        "priority": "u=0, i",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    }

    url = args.url
    output_dir = args.output_dir
    api_key = args.api_key or os.environ.get("YANDEX_GEOCODER_API_KEY")

    if not os.path.isdir(output_dir):
        print(f"""Ошибка: Указанная папка \'{output_dir}\' не существует.""")
        return

    print(f"""Получение данных с URL: {url}""")
    data = ""
    parsed_url = urlparse(url)
    if parsed_url.scheme == "file":
        try:
            if os.name == "nt" and parsed_url.path.startswith("/"):
                path = parsed_url.path[1:]
            with open(path, "r", encoding="utf-8") as f:
                data = f.read()
        except IOError as e:
            print(f"""Ошибка при чтении локального файла {path}: {e}""")
            return
    else:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Проверка на ошибки HTTP
            data = response.text
        except requests.exceptions.RequestException as e:
            print(f"""Ошибка при получении данных: {e}""")
            return

    # Регулярное выражение для извлечения текста между <script> и </script>
    pattern = r'<script type="application/json" class="state-view">\s*(.*?)\s*</script>'
    match = re.search(pattern, data, re.DOTALL)

    script_content = ""
    if match:
        script_content = match.group(1)
    else:
        print("Скрипт не найден.")

    data_json = json.loads(script_content)

    # print(f"script_content: {script_content}")

    if not data_json:
        print(
            """Ошибка: Не удалось найти или распарсить JSON с \'bookmarksPublicList\' в ответе."""
        )
        return

    bookmarks_list = data_json.get("config").get("bookmarksPublicList")
    if not bookmarks_list:
        print("""Ошибка: Ключ \'bookmarksPublicList\' не найден в JSON.""")
        return

    list_rev = bookmarks_list.get("revision", -1)
    list_publicid = bookmarks_list.get("publicId")
    list_title = bookmarks_list.get("title", "Без названия")
    list_desc = bookmarks_list.get("description")
    list_author = bookmarks_list.get("author")
    children = bookmarks_list.get("children", [])

    list_title += " rev:" + str(list_rev)

    cleaned_list_title = list_title.replace(" ", "_").replace(":", "_")
    filename = os.path.join(output_dir, f"{cleaned_list_title}.gpx")
    print(f"filename: {filename}")

    if not children:
        print("""Нет точек для сохранения.""")
        return

    ns = {
        "": "http://www.topografix.com/GPX/1/1",
        "yandex": "https://yandex.ru",
        "osmand": "https://osmand.net",
        "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    }

    wpts = []
    if os.path.exists(filename):
        for key in ns:
            ET.register_namespace(key, ns[key])
        root = ET.parse(filename)
        wpts = root.getroot().findall("wpt", ns)

    gpx_root = ET.Element(
        "gpx",
        version="1.1",
        creator="gpx_converter",
        xmlns="http://www.topografix.com/GPX/1/1",
        attrib={
            "xmlns:yandex": "https://yandex.ru",
            "xmlns:osmand": "https://osmand.net",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:schemaLocation": "http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd",
        },
    )

    metadata = gpx_root.findall("metadata", ns)
    for item in metadata:
        gpx_root.remove(item)

    metadata = ET.SubElement(gpx_root, "metadata")
    ET.SubElement(metadata, "name").text = list_title
    ET.SubElement(metadata, "desc").text = list_desc
    metadata_author = ET.SubElement(metadata, "author")
    ET.SubElement(metadata_author, "name").text = list_author

    metadata_extensions = ET.SubElement(metadata, "extensions")
    ET.SubElement(metadata_extensions, "yandex:revision").text = str(list_rev)
    ET.SubElement(metadata_extensions, "yandex:publicId").text = list_publicid

    for item in children:
        print(f"item: {item}")
        uri = item.get("uri")
        title = item.get("title", "Без названия")
        description = item.get("description", "")
        uri = item.get("uri")
        # print(f"description: {description}")

        found = False
        for wpt in wpts:
            exts = wpt.find("extensions", ns)
            if exts is None:
                continue
            wpt_uri = exts.find("yandex:uri", ns)
            if wpt_uri is not None and wpt_uri.text == uri:
                print(f"SKIP {item}")
                found = True
                continue

        if found:
            ET.SubElement(gpx_root, "wpt")
            continue

        lat, lon = None, None
        address = "Адрес не определён"

        if uri and "ymapsbm1://pin?ll=" in uri:
            coords_str = unquote(uri.split("ll=")[1])
            lon, lat = map(float, coords_str.split(","))
        elif uri and "ymapsbm1://org?oid=" in uri:
            if not api_key:
                print(
                    """Предупреждение: API ключ для Яндекс Геокодера не установлен. Невозможно получить координаты для org?oid."""
                )
                continue

            geocoder_url = f"https://geocode-maps.yandex.ru/v1/?apikey={api_key}&uri={
                uri
            }&format=json&language=ru_RU"
            try:
                print("Получение данных объекта из геокодера: " + geocoder_url)
                geo_response = requests.get(geocoder_url)
                geo_response.raise_for_status()
                geo_data = geo_response.json()
                print(f"geo_data: {geo_data}")

                pos = geo_data["response"]["GeoObjectCollection"]["featureMember"][0][
                    "GeoObject"
                ]["Point"]["pos"]
                lon, lat = map(float, pos.split(" "))

                full_address = geo_data["response"]["GeoObjectCollection"][
                    "featureMember"
                ][0]["GeoObject"]["metaDataProperty"]["GeocoderMetaData"]["text"]
                address = full_address if full_address else address

            except requests.exceptions.RequestException as e:
                print(f"""Ошибка при запросе к геокодеру для {uri}: {e}""")
                if e.response.status_code == 403:
                    print(f"\n\n\tFORBIDDEN ERROR {list_title}\n\n")
                    break
                continue
            except (KeyError, IndexError) as e:
                print(f"""Ошибка парсинга ответа геокодера для {uri}: {e}""")
                continue

        if lat is not None and lon is not None:
            wpt = ET.SubElement(gpx_root, "wpt", lat=str(lat), lon=str(lon))
            ET.SubElement(wpt, "name").text = title
            ET.SubElement(wpt, "type").text = list_title
            extensions = ET.SubElement(wpt, "extensions")
            ET.SubElement(extensions, "author").text = list_author
            ET.SubElement(extensions, "osmand:address").text = address
            ET.SubElement(extensions, "yandex:uri").text = uri

    tree = ET.ElementTree(gpx_root)
    ET.indent(tree, space="  ", level=0)  # Для красивого форматирования XML

    tree.write(filename, encoding="UTF-8", xml_declaration=True)
    print(f"""GPX файл успешно сохранен: {filename}""")


if __name__ == "__main__":
    main()
