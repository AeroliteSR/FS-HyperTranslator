import random
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from googletrans import LANGUAGES, Translator
import tempfile
from collections import defaultdict

PATH = r"C:\Users\Aero\Downloads\HyperTranslate" # path to file or folder to process in main()
TRANSLATION_TIMES = 6 # how many times to hypertranslate
MAX_CONCURRENT_TRANSLATIONS = 5 # how many translations to do at once
# try to keep the product of these numbers below 50 or you might get rate limited by google

STARTING_LANGUAGE = "English"
FINAL_LANGUAGE = "English"

# Dont change:
CACHE_FILE = Path(sys.argv[0]).parent / "translation_cache.json"
translator = Translator()
languages = [lang for lang in LANGUAGES if lang != STARTING_LANGUAGE]
semaphore = asyncio.Semaphore(MAX_CONCURRENT_TRANSLATIONS)

RerollOverride = { # a way to guarantee certain past translations if you like them
    "The Dragon's Heritage.": "Germany will be ours."
}

def save_cache():
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

async def translate(text: str, src: str, dest: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            return await translator.translate(text, src=src, dest=dest)
        except Exception as e:
            print(e)
            
            if attempt == retries - 1:
                save_cache() # save cached data if rate limited to restart from
                raise
            await asyncio.sleep(0.3 * (attempt + 1))

async def processHyperTranslations(text: str, text_id: int, name: str) -> str:
    global cache
    text_id = str(text_id) # json.dump converts integer keys to strings

    if not text or not len(set(text)) > 1 or text == '<?null?>':
        return text
    
    if text in RerollOverride:
        return RerollOverride[text]

    if text_id in cache[name]:
        print(f'Skipping from cache; {name} - id {text_id}')
        return cache[name][text_id]

    async with semaphore:
        src = STARTING_LANGUAGE
        current = text

        for _ in range(TRANSLATION_TIMES - 1):
            dest = random.choice(languages)
            result = await translate(current, src, dest)
            current = result.text
            src = dest

        final = await translate(current, src, FINAL_LANGUAGE)
        translated = final.text

        cache[name][text_id] = translated
        print(f"{text} translated to: {final.text}")
        save_cache() # NOTE: uncomment to backup cache on every translation

        return translated

async def replaceFields(data: Any, name: str | None = None) -> Any:
    if isinstance(data, dict):
        new = {}

        if isinstance(data.get("Name"), str):
            name = data["Name"]
        
        text = data.get("Text")
        text_id = data.get("ID")

        for k, v in data.items():
            if (k == "Text" and isinstance(text, str) and isinstance(text_id, int) and name is not None):
                new[k] = await processHyperTranslations(text, text_id, name)
            else:
                new[k] = await replaceFields(v, name)

        return new

    if isinstance(data, list):
        return [await replaceFields(item, name) for item in data]

    return data

async def processFile(file_input: str, file_output: str):
    if os.path.exists(file_output):
        print(f"Skipping completed file: {file_output}")
        return

    with open(file_input, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated_data = await replaceFields(data)

    out_dir = os.path.dirname(file_output)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=out_dir, delete=False) as tmp:
        json.dump(updated_data, tmp, ensure_ascii=False, indent=2)
        temp_name = tmp.name

    os.replace(temp_name, file_output)

async def processFolder(folder: str, suffix="_updated"):
    for filename in os.listdir(folder):
        if filename.lower().endswith(".json"):
            src = os.path.join(folder, filename)
            name, ext = os.path.splitext(filename)
            dst = os.path.join(folder, f"{name}{suffix}{ext}")
            await processFile(src, dst)

async def main():
    try:
        await processFolder(PATH)
    except Exception as e:
        print(e)
        save_cache()
        await asyncio.sleep(10.0)
        await main()

if __name__ == "__main__":
    cache: dict[str, dict[str, str]] = defaultdict(dict)

    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)

    asyncio.run(main())