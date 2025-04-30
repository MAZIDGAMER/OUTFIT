from flask import Flask, request, send_file, Response
from PIL import Image, ImageDraw, ImageFont
import requests
import io
import concurrent.futures
import time
import textwrap
import os
from io import BytesIO
import json
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ASSET_BASE_URL = "https://freefireassetskeymg00.mazidgamer.xyz"
ITEM_FOLDER = "FF%20ITEMS"
TEMPLATE_URL = f"{ASSET_BASE_URL}/template.png"

# Cache expiry times
IMAGE_CACHE_EXPIRY = 86400  # 24 hours for all images

# Default positions for items
DEFAULT_POSITIONS = {
    'character': {'position': (660, 750), 'size': (800, 1000)},
    'head': [
        {'position': (954, 256), 'size': (200, 200)},  # Head item 1
        {'position': (1130, 496), 'size': (200, 200)}  # Head item 2
    ],
    'mask': [
        {'position': (1182, 270), 'size': (200, 200)}  # Mask item
    ],
    'top': [
        {'position': (180, 508), 'size': (200, 200)},  # Top item 1
        {'position': (324, 254), 'size': (200, 200)}   # Top item 2
    ],
    'bottom': [
        {'position': (170, 796), 'size': (200, 200)}   # Bottom item
    ],
    'footwear': [
        {'position': (326, 1028), 'size': (200, 200)}  # Footwear item
    ],
    'weapons': [
        {'position': (1056, 794), 'size': (500, 150)},  # Weapon item 1
        {'position': (1156, 894), 'size': (500, 150)}   # Weapon item 2
    ],
    'pets': [
        {'position': (952, 1052), 'size': (150, 150)}   # Pet item
    ],
    'name': {'position': (638, 164), 'max_width': 500}  # Name position
}

# Weapon stretching configurations
WEAPON_STRETCH = {
    'default': {'width': 500, 'height': 150},
    'custom': {
        '907101817': {'width': 500, 'height': 150},  # Default weapon 1
        '907101818': {'width': 500, 'height': 150}   # Default weapon 2
    }
}

# Font settings
FONT_URL = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf"
FONT_SIZE = 40
FONT_COLOR = (255, 255, 255)
OUTLINE_COLOR = (0, 0, 0)
OUTLINE_WIDTH = 2

# Custom character configurations
CHARACTER_CONFIGS = {
    '102000024': {'position': (650, 750), 'size': (750, 900)},
    '102000004': {'position': (650, 720), 'size': (700, 1000)},
    '101000006': {'position': (720, 750), 'size': (750, 1000)},
    '101000020': {'position': (630, 750), 'size': (800, 1000)},
    '101000023': {'position': (680, 750), 'size': (750, 950)},
    '101000026': {'position': (650, 750), 'size': (800, 900)},
    '101000027': {'position': (665, 720), 'size': (750, 850)},
    '102000010': {'position': (720, 750), 'size': (800, 1000)},
    '102000017': {'position': (650, 750), 'size': (650, 950)},
    '102000022': {'position': (650, 750), 'size': (650, 950)},
    '102000027': {'position': (650, 750), 'size': (650, 950)},
    '102000029': {'position': (600, 750), 'size': (750, 1000)},
    '102000036': {'position': (630, 750), 'size': (700, 1000)},
    '102000041': {'position': (650, 750), 'size': (500, 900)}
}

# All available categories
CATEGORIES = {
    'head': 'head',
    'mask': 'mask',
    'top': 'top',
    'bottom': 'bottom',
    'footwear': 'footwear',
    'weapons': 'weapons',
    'pets': 'pets',
    'character': 'character'
}

# Default items for all outfit categories and weapons
DEFAULT_ITEMS = {
    'head': ["907100011", "907100013"],
    'mask': ["214000000"],
    'top': ["203000000", "908100013"],
    'bottom': ["909100001"],
    'footwear': ["910100001"],
    'weapons': ["907101817", "907101818"]
}

# Global caches
ITEM_CATEGORIES = {}
ITEM_CATEGORY_CACHE = {}
IMAGE_CACHE = {}
FONT_CACHE = None

# Load item_categories.json at startup
try:
    with open("item_categories.json", 'r') as f:
        ITEM_CATEGORIES = json.load(f)
except FileNotFoundError:
    logger.warning("item_categories.json not found")
except json.JSONDecodeError:
    logger.warning("item_categories.json is invalid JSON")

# Preload template image at startup
def preload_template():
    logger.info("Preloading template image")
    start_time = time.time()
    img = download_image(TEMPLATE_URL)
    if img:
        logger.info(f"Template preloaded in {time.time() - start_time:.2f}s")
    else:
        logger.error("Failed to preload template image")

# Preload font at startup
def preload_font():
    global FONT_CACHE
    logger.info("Preloading font")
    start_time = time.time()
    try:
        font_response = requests.get(FONT_URL, timeout=5)
        font_response.raise_for_status()
        font_data = BytesIO(font_response.content)
        FONT_CACHE = ImageFont.truetype(font_data, FONT_SIZE)
        logger.info(f"Font preloaded in {time.time() - start_time:.2f}s")
    except Exception as e:
        logger.warning(f"Failed to download font: {e}")
        try:
            FONT_CACHE = ImageFont.truetype("arial.ttf", FONT_SIZE)
            logger.info("Using local arial.ttf font")
        except:
            FONT_CACHE = ImageFont.load_default()
            logger.info("Using default font")

def get_font():
    return FONT_CACHE

def find_item_category(item_id):
    cached = ITEM_CATEGORY_CACHE.get(item_id)
    if cached and time.time() - cached['time'] < IMAGE_CACHE_EXPIRY:
        return cached['category']
    
    category = ITEM_CATEGORIES.get(item_id)
    ITEM_CATEGORY_CACHE[item_id] = {'category': category, 'time': time.time()}
    return category

def download_image(url):
    cached = IMAGE_CACHE.get(url)
    if cached and time.time() - cached['time'] < IMAGE_CACHE_EXPIRY:
        return Image.open(BytesIO(cached['data'])).convert("RGBA")
    
    try:
        start_time = time.time()
        r = requests.get(url, timeout=2)
        r.raise_for_status()
        img_data = r.content
        IMAGE_CACHE[url] = {'data': img_data, 'time': time.time()}
        logger.info(f"Downloaded {url} in {time.time() - start_time:.2f}s")
        return Image.open(BytesIO(img_data)).convert("RGBA")
    except Exception as e:
        logger.error(f"Error downloading {url}: {e}")
        return None

def draw_text_with_outline(draw, position, text, font, text_color, outline_color, outline_width):
    x, y = position
    for dx in [-outline_width, 0, outline_width]:
        for dy in [-outline_width, 0, outline_width]:
            if dx != 0 or dy != 0:
                draw.text((x+dx, y+dy), text, font=font, fill=outline_color)
    draw.text(position, text, font=font, fill=text_color)

# Preload assets at startup
preload_template()
preload_font()

@app.route("/render-image")
def render_image():
    start_time = time.time()
    logger.info("Starting image rendering")

    avatar_id = request.args.get("avatarId")
    outfits = request.args.get("outfits", "")
    weapons = request.args.get("weapons", "")
    pets = request.args.get("pets", "")
    player_name = request.args.get("player_name", "").strip()

    if not avatar_id:
        logger.error("Missing avatarId")
        return Response("Missing avatarId", status=400)

    # Initialize category items
    category_items = {
        'head': [],
        'mask': [],
        'top': [],
        'bottom': [],
        'footwear': [],
        'weapons': [],
        'pets': []
    }

    # Process weapons (limit to 2)
    process_start = time.time()
    for weapon in [w.strip() for w in weapons.split(",") if w.strip()][:2]:
        if weapon:
            category_items['weapons'].append(weapon)

    # Process pets (limit to 1)
    for pet in [p.strip() for p in pets.split(",") if p.strip()][:1]:
        if pet:
            category_items['pets'].append(pet)

    # Process outfits (limit to 7 total)
    outfit_items = [item.strip() for item in outfits.split(",") if w.strip()][:7]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        category_results = list(executor.map(find_item_category, outfit_items))
    
    for item_id, category in zip(outfit_items, category_results):
        if category and category in category_items:
            if len(category_items[category]) < len(DEFAULT_POSITIONS[category]):
                category_items[category].append(item_id)
    logger.info(f"Item processing took {time.time() - process_start:.2f}s")

    # Apply default items where needed
    default_start = time.time()
    for category in ['head', 'top', 'weapons']:
        current_items = category_items[category]
        required_count = len(DEFAULT_POSITIONS[category])
        if len(current_items) < required_count:
            for default_item in DEFAULT_ITEMS.get(category, [])[:required_count - len(current_items)]:
                if default_item not in current_items:
                    category_items[category].append(default_item)
        elif len(current_items) > required_count:
            category_items[category] = current_items[:required_count]

    for category in ['mask', 'bottom', 'footwear']:
        current_items = category_items[category]
        required_count = len(DEFAULT_POSITIONS[category])
        if len(current_items) < required_count:
            for default_item in DEFAULT_ITEMS.get(category, [])[:required_count - len(current_items)]:
                if default_item not in current_items:
                    category_items[category].append(default_item)
        elif len(current_items) > required_count:
            category_items[category] = current_items[:required_count]
    logger.info(f"Default item application took {time.time() - default_start:.2f}s")

    # Load all images concurrently
    download_start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            (executor.submit(download_image, TEMPLATE_URL), 'template', None, None)
        ]
        if avatar_id:
            futures.append(
                (executor.submit(download_image, f"{ASSET_BASE_URL}/{ITEM_FOLDER}/{avatar_id}.png"), 'avatar', None, avatar_id)
            )
        
        for category, items in category_items.items():
            for i, item_id in enumerate(items[:len(DEFAULT_POSITIONS[category])]):
                futures.append(
                    (executor.submit(download_image, f"{ASSET_BASE_URL}/{ITEM_FOLDER}/{item_id}.png"), category, i, item_id)
                )

        # Collect results
        template = None
        avatar = None
        item_images = []
        for future, target, pos_idx, item_id in futures:
            img = future.result()
            if target == 'template':
                template = img
            elif target == 'avatar':
                avatar = img
            elif img:
                item_images.append((img, target, pos_idx, item_id))
    logger.info(f"Image downloading took {time.time() - download_start:.2f}s")

    if not template:
        logger.error("Failed to load template")
        return Response("Failed to load template", status=500)

    # Apply character customization
    render_start = time.time()
    if avatar:
        char_config = CHARACTER_CONFIGS.get(avatar_id, DEFAULT_POSITIONS['character'])
        avatar = avatar.resize(char_config['size'], resample=Image.LANCZOS)
        pos = char_config['position']
        template.paste(avatar, (pos[0] - avatar.width // 2, pos[1] - avatar.height // 2), avatar)

    # Process all items
    for img, category, pos_idx, item_id in item_images:
        pos_config = DEFAULT_POSITIONS[category][pos_idx]
        if category == 'weapons':
            weapon_size = WEAPON_STRETCH['custom'].get(item_id, WEAPON_STRETCH['default'])
            img = img.resize((weapon_size['width'], weapon_size['height']), resample=Image.LANCZOS)
        else:
            img = img.resize(pos_config['size'], resample=Image.LANCZOS)
        pos = pos_config['position']
        template.paste(img, (pos[0] - img.width // 2, pos[1] - img.height // 2), img)

    # Add player name if provided
    if player_name:
        draw = ImageDraw.Draw(template)
        font = get_font()
        max_width = DEFAULT_POSITIONS['name']['max_width']
        avg_char_width = font.getlength("A")
        max_chars = int(max_width / avg_char_width)
        
        if font.getlength(player_name) > max_width:
            wrapped_text = textwrap.fill(player_name, width=max_chars)
        else:
            wrapped_text = player_name
        
        text_bbox = draw.textbbox((0, 0), wrapped_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        x = DEFAULT_POSITIONS['name']['position'][0] - text_width // 2
        y = DEFAULT_POSITIONS['name']['position'][1] - text_height // 2
        
        draw_text_with_outline(
            draw, (x, y), wrapped_text, font,
            FONT_COLOR, OUTLINE_COLOR, OUTLINE_WIDTH
        )
    logger.info(f"Image rendering took {time.time() - render_start:.2f}s")

    # Save and return image
    output_start = time.time()
    output = io.BytesIO()
    template.save(output, "PNG", optimize=True)
    output.seek(0)
    logger.info(f"Image saving took {time.time() - output_start:.2f}s")
    logger.info(f"Total request took {time.time() - start_time:.2f}s")

    return send_file(output, mimetype="image/png")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
