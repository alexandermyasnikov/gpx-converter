import argparse
import requests
import json
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse
import os
import re
from bs4 import BeautifulSoup
from dotenv import load_dotenv

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="""Консольная утилита для конвертации закладок Яндекс Карт в GPX.""")
    parser.add_argument("url", type=str, help="""URL для получения данных.""")
    parser.add_argument("output_dir", type=str, help="""Путь к папке для сохранения GPX файла.""")
    parser.add_argument("--api_key", type=str, help="""API ключ для Яндекс Геокодера. Если не указан, будет использована переменная окружения YANDEX_GEOCODER_API_KEY.""")
    args = parser.parse_args()

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
            if os.name == 'nt' and parsed_url.path.startswith('/'):
                path = parsed_url.path[1:]
            with open(path, "r", encoding="utf-8") as f:
                data = f.read()
        except IOError as e:
            print(f"""Ошибка при чтении локального файла {path}: {e}""")
            return
    else:
        try:
            response = requests.get(url)
            response.raise_for_status()  # Проверка на ошибки HTTP
            data = response.text
        except requests.exceptions.RequestException as e:
            print(f"""Ошибка при получении данных: {e}""")
            return

    # Регулярное выражение для извлечения текста между <script> и </script>
    pattern = r'<script type="application/json" class="state-view">\s*(.*?)\s*</script>'
    match = re.search(pattern, data, re.DOTALL)

    script_content = ''
    if match:
        script_content = match.group(1)
    else:
        print("Скрипт не найден.")

    data_json = json.loads(script_content)

    # # Используем BeautifulSoup для извлечения JSON из HTML
    # soup = BeautifulSoup(script_content, 'html.parser')
    # script_tag = soup.find('script', {'type': 'application/json'})
    # data_json = None
    # if script_tag:
    #     try:
    #         data_json = json.loads(script_tag.string)
    #     except json.JSONDecodeError as e:
    #         print(f"""Ошибка при парсинге JSON из script тега: {e}""")
    #         return

    if not data_json:
        print("""Ошибка: Не удалось найти или распарсить JSON с \'bookmarksPublicList\' в ответе.""")
        return

    bookmarks_list = data_json.get("config").get("bookmarksPublicList")
    if not bookmarks_list:
        print("""Ошибка: Ключ \'bookmarksPublicList\' не найден в JSON.""")
        return

    list_title = bookmarks_list.get("title", "Без названия")
    children = bookmarks_list.get("children", [])

    if not children:
        print("""Нет точек для сохранения.""")
        return

    gpx_root = ET.Element("gpx", version="1.1", creator="Manus",
                          xmlns="http://www.topografix.com/GPX/1/1",
                          attrib={
                              "xmlns:osmand": "https://osmand.net",
                              "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                              "xsi:schemaLocation": "http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd"
                          })

    metadata = ET.SubElement(gpx_root, "metadata")
    ET.SubElement(metadata, "name").text = list_title

    for item in children:
        uri = item.get("uri")
        title = item.get("title", "Без названия")
        description = item.get("description", "")

        lat, lon = None, None
        address = "Адрес не определён"

        if uri and "ymapsbm1://pin?ll=" in uri:
            coords_str = unquote(uri.split("ll=")[1])
            lon, lat = map(float, coords_str.split(","))
        elif uri and "ymapsbm1://org?oid=" in uri:
            if not api_key:
                print("""Предупреждение: API ключ для Яндекс Геокодера не установлен. Невозможно получить координаты для org?oid.""")
                continue

            geocoder_url = f"https://geocode-maps.yandex.ru/v1/?apikey={api_key}&uri={uri}&format=json&language=ru_RU"
            try:
                geo_response = requests.get(geocoder_url)
                geo_response.raise_for_status()
                geo_data = geo_response.json()

                pos = geo_data["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["Point"]["pos"]
                lon, lat = map(float, pos.split(" "))

                full_address = geo_data["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["metaDataProperty"]["GeocoderMetaData"]["text"]
                address = full_address if full_address else address

            except requests.exceptions.RequestException as e:
                print(f"""Ошибка при запросе к геокодеру для {uri}: {e}""")
                continue
            except (KeyError, IndexError) as e:
                print(f"""Ошибка парсинга ответа геокодера для {uri}: {e}""")
                continue

        if lat is not None and lon is not None:
            wpt = ET.SubElement(gpx_root, "wpt", lat=str(lat), lon=str(lon))
            ET.SubElement(wpt, "name").text = title
            ET.SubElement(wpt, "type").text = list_title
            extensions = ET.SubElement(wpt, "extensions")
            osmand_address = ET.SubElement(extensions, "osmand:address")
            osmand_address.text = address

    tree = ET.ElementTree(gpx_root)
    ET.indent(tree, space="  ", level=0) # Для красивого форматирования XML

    cleaned_list_title = list_title.replace(" ", "_")
    output_filename = os.path.join(output_dir, f"{cleaned_list_title}.gpx")
    tree.write(output_filename, encoding="UTF-8", xml_declaration=True)
    print(f"""GPX файл успешно сохранен: {output_filename}""")

if __name__ == "__main__":
    main()


