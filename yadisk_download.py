#!/usr/bin/env python3
"""
Скачивание публичной папки с Яндекс Диска без авторизации.
Использование: python yadisk_download.py <ссылка> [папка назначения]
"""

import sys
import os
import json
import urllib.request
import urllib.parse
import urllib.error
import socket
import time

API = "https://cloud-api.yandex.net/v1/disk/public/resources"


def fetch_with_retry(url, timeout=30, retries=5, backoff=3):
    """Выполняет GET-запрос с повторными попытками при сетевых сбоях/таймаутах."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (TimeoutError, socket.timeout, urllib.error.URLError) as e:
            last_err = e
            wait = backoff * attempt
            print(f"  сетевая ошибка ({e}), повтор {attempt}/{retries} через {wait}с...")
            time.sleep(wait)
    raise last_err


def get_items(public_key, path="/", offset=0, limit=100):
    params = urllib.parse.urlencode({
        "public_key": public_key,
        "path": path,
        "offset": offset,
        "limit": limit,
        "fields": "_embedded.items.name,_embedded.items.type,_embedded.items.path,"
                  "_embedded.items.file,_embedded.items.size,_embedded.total"
    })
    url = f"{API}?{params}"
    return json.loads(fetch_with_retry(url, timeout=30))


def get_download_url(public_key, path):
    params = urllib.parse.urlencode({"public_key": public_key, "path": path})
    url = f"{API}/download?{params}"
    return json.loads(fetch_with_retry(url, timeout=30))["href"]


def download_file(url, dest_path):
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    last_err = None
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r, open(dest_path, "wb") as f:
                total = int(r.headers.get("Content-Length", 0))
                downloaded = 0
                while chunk := r.read(1024 * 256):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        mb = downloaded / 1024 / 1024
                        print(f"\r  {pct}% ({mb:.1f} MB)", end="", flush=True)
            print()
            return
        except (TimeoutError, socket.timeout, urllib.error.URLError) as e:
            last_err = e
            wait = 3 * attempt
            print(f"\n  сетевая ошибка при скачивании ({e}), повтор {attempt}/3 через {wait}с...")
            time.sleep(wait)
    raise last_err


def list_all(public_key, path="/"):
    """Рекурсивно получить все файлы."""
    offset = 0
    limit = 100
    files = []
    while True:
        data = get_items(public_key, path, offset, limit)
        emb = data.get("_embedded", {})
        items = emb.get("items", [])
        total = emb.get("total", 0)
        for item in items:
            if item["type"] == "file":
                files.append(item)
            elif item["type"] == "dir":
                files.extend(list_all(public_key, item["path"]))
        offset += len(items)
        if offset >= total:
            break
    return files


def main():
    if len(sys.argv) < 2:
        print("Использование: python yadisk_download.py <ссылка> [папка]")
        sys.exit(1)

    public_key = sys.argv[1]
    dest_dir = sys.argv[2] if len(sys.argv) > 2 else "downloaded"

    print(f"Получаю список файлов...")
    try:
        files = list_all(public_key)
    except urllib.error.HTTPError as e:
        print(f"Ошибка API: {e.code} {e.reason}")
        sys.exit(1)

    if not files:
        print("Файлов не найдено (возможно, это одиночный файл).")
        # Попробовать скачать как одиночный файл
        try:
            dl_url = get_download_url(public_key, "/")
            name = os.path.join(dest_dir, "file")
            os.makedirs(dest_dir, exist_ok=True)
            print(f"Скачиваю файл -> {name}")
            download_file(dl_url, name)
        except Exception as e:
            print(f"Ошибка: {e}")
        return

    total_size = sum(f.get("size", 0) for f in files)
    print(f"Найдено файлов: {len(files)}, общий размер: {total_size/1024/1024:.1f} МБ")
    print()

    for i, item in enumerate(files, 1):
        rel_path = item["path"].lstrip("/")
        dest_path = os.path.join(dest_dir, rel_path)

        print(f"[{i}/{len(files)}] {rel_path}")
        if os.path.exists(dest_path) and os.path.getsize(dest_path) == item.get("size", -1):
            print("  пропускаю (уже скачан)")
            continue
        try:
            dl_url = get_download_url(public_key, item["path"])
            download_file(dl_url, dest_path)
        except Exception as e:
            print(f"  ОШИБКА: {e}")

    print(f"\nГотово! Файлы сохранены в: {os.path.abspath(dest_dir)}")


if __name__ == "__main__":
    main()