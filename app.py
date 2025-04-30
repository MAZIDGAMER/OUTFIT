from flask import Flask, request, send_file, Response
from PIL import Image, ImageDraw, ImageFont
import requests
import io
import concurrent.futures
import time
import textwrap
from io import BytesIO

app = Flask(__name__)

ASSET_BASE_URL = "https://www.freefireassetskeymg00.mazidgamer.xyz/public_html"
DATA_API_URL = "https://mazidgmrinfoapi.vercel.app/get?uid={uid}&region={region}"

# Default positions and sizes for all items
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
        {'position': (180, 508), 'size': (200, 200)},   # Top item 1
        {'position': (324, 254), 'size': (200, 200)}    # Top item 2
    ],
    'bottom': [
        {'position': (170, 796), 'size': (200, 200)}   # Bottom item
    ],
    'footwear': [
        {'position': (326, 1028), 'size': (200, 200)}   # Footwear item
    ],
    'weapons': [
        {'position': (1056, 815), 'size': (500, 150)}  # Weapon item
    ],
    'pets': [
        {'position': (952, 1052), 'size': (150, 150)}   # Pet item
    ],
    'name': {'position': (638, 164), 'max_width': 500}  # Name position
}

# Default items
DEFAULT_ITEMS = {
    'character': '102000019',
    'mask': '214000000',
    'top': '203000000',
    'weapons': '907101817',
    'pets': '1300000113'
}

# Weapon stretching configurations
WEAPON_STRETCH = {
    'default': {'width': 500, 'height': 150},
    'custom': {
        'xyz': {'width': 250, 'height': 180},  # Custom weapon sizes
        'xyz': {'width': 300, 'height': 150}
    }
}

# Font settings (Universal Font Support)
FONT_URL = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf"  # Supports almost all Unicode
FONT_SIZE = 40
FONT_COLOR = (255, 255, 255)  # Gold color for player name
OUTLINE_COLOR = (0, 0, 0)  # Dark blue outline
OUTLINE_WIDTH = 2

# Custom character configurations
CHARACTER_CONFIGS = {
    '102000024': {'position': (650, 750), 'size': (750, 900)},
    '102000004': {'position': (660, 720), 'size': (500, 1150)},
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
    'character': 'characters'
}

ITEM_CATEGORY_CACHE = {}
CACHE_EXPIRY = 300
FONT_CACHE = None
PLAYER_DATA_CACHE = {}
PLAYER_DATA_CACHE_EXPIRY = 600  # 10 minutes cache for player data

def get_font():
    global FONT_CACHE
    if not FONT_CACHE:
        try:
            # Try to download Noto Sans (supports almost all Unicode)
            font_response = requests.get(FONT_URL, timeout=5)
            font_data = BytesIO(font_response.content)
            FONT_CACHE = ImageFont.truetype(font_data, FONT_SIZE)
        except:
            try:
                # Fallback to Arial (if available)
                FONT_CACHE = ImageFont.truetype("arial.ttf", FONT_SIZE)
            except:
                # Final fallback (may not support all characters)
                FONT_CACHE = ImageFont.load_default()
    return FONT_CACHE

def find_item_category(item_id):
    cached = ITEM_CATEGORY_CACHE.get(item_id)
    if cached and time.time() - cached['time'] < CACHE_EXPIRY:
        return cached['category']
    
    def check_category(category):
        url = f"{ASSET_BASE_URL}/{CATEGORIES[category]}/{item_id}.png"
        try:
            response = requests.head(url, timeout=2)
            if response.status_code == 200:
                return category
        except:
            pass
        return None

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(check_category, cat): cat for cat in CATEGORIES if cat != 'character'}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                ITEM_CATEGORY_CACHE[item_id] = {'category': result, 'time': time.time()}
                return result
    
    ITEM_CATEGORY_CACHE[item_id] = {'category': None, 'time': time.time()}
    return None

def download_image(url):
    try:
        r = requests.get(url, timeout=4)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return None

def draw_text_with_outline(draw, position, text, font, text_color, outline_color, outline_width):
    x, y = position
    # Draw outline
    for dx in [-outline_width, 0, outline_width]:
        for dy in [-outline_width, 0, outline_width]:
            if dx != 0 or dy != 0:
                draw.text((x+dx, y+dy), text, font=font, fill=outline_color)
    # Draw main text
    draw.text(position, text, font=font, fill=text_color)

def fetch_player_data(uid, region):
    cache_key = f"{uid}_{region}"
    cached_data = PLAYER_DATA_CACHE.get(cache_key)
    
    if cached_data and time.time() - cached_data['time'] < PLAYER_DATA_CACHE_EXPIRY:
        return cached_data['data']
    
    try:
        # Add retry mechanism for API requests
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    DATA_API_URL.format(uid=uid, region=region),
                    timeout=5,
                    headers={
                        'User-Agent': 'FreeFireOutfitRenderer/1.0',
                        'Accept': 'application/json'
                    }
                )
                
                # Check for rate limiting
                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))
                        continue
                    else:
                        response.raise_for_status()
                
                response.raise_for_status()
                data = response.json()
                
                # Validate and normalize the response data
                if not isinstance(data, dict):
                    raise ValueError("Invalid API response format")
                
                profile_info = data.get("profileInfo", {})
                basic_info = data.get("basicInfo", {})
                pet_info = data.get("petInfo", {})
                
                result = {
                    "avatar_id": str(profile_info.get("avatarId", DEFAULT_ITEMS['character'])),
                    "outfits": profile_info.get("equippedSkills", []),
                    "weapons": basic_info.get("weaponSkinShows", [DEFAULT_ITEMS['weapons']]),
                    "pets": [str(pet_info.get("petId", DEFAULT_ITEMS['pets']))],
                    "player_name": basic_info.get("nickname", "").strip()
                }
                
                # Cache the successful response
                PLAYER_DATA_CACHE[cache_key] = {
                    'data': result,
                    'time': time.time()
                }
                
                return result
                
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    print(f"Failed to fetch player data after {max_retries} attempts: {e}")
                    return None
                time.sleep(retry_delay * (attempt + 1))
                
    except Exception as e:
        print(f"Error processing player data: {e}")
        return None

@app.route("/render-image")
def render_image():
    start_time = time.time()

    uid = request.args.get("uid")
    region = request.args.get("region")

    if not uid or not region:
        return Response("Missing UID or region", status=400)

    # Fetch player data from API with enhanced error handling
    player_data = fetch_player_data(uid, region)
    if not player_data:
        # Fallback to default items if API fails
        player_data = {
            "avatar_id": DEFAULT_ITEMS['character'],
            "outfits": [],
            "weapons": [DEFAULT_ITEMS['weapons']],
            "pets": [DEFAULT_ITEMS['pets']],
            "player_name": f"Player {uid}"
        }

    avatar_id = player_data["avatar_id"]
    outfits = player_data["outfits"]
    weapons = player_data["weapons"]
    pets = player_data["pets"]
    player_name = player_data["player_name"]

    # Prepare items by category
    category_items = {
        'head': [],
        'mask': [],
        'top': [],
        'bottom': [],
        'footwear': [],
        'weapons': [],
        'pets': []
    }

    # Process weapons and pets
    for weapon in weapons[:1]:
        category_items['weapons'].append(str(weapon))
    
    for pet in pets[:1]:
        category_items['pets'].append(str(pet))

    # Process outfits
    outfit_items = [str(item) for item in outfits]
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        category_results = list(executor.map(find_item_category, outfit_items))
    
    for item_id, category in zip(outfit_items, category_results):
        if category and category in category_items:
            if len(category_items[category]) < len(DEFAULT_POSITIONS[category]):
                category_items[category].append(item_id)

    # Apply defaults for missing items
    if not category_items['mask']:
        category_items['mask'].append(DEFAULT_ITEMS['mask'])
    
    # Special handling for tops - if only 1 top available, add default as second top
    if len(category_items['top']) == 1:
        category_items['top'].append(DEFAULT_ITEMS['top'])

    # Load template and avatar
    with concurrent.futures.ThreadPoolExecutor() as executor:
        template_f = executor.submit(download_image, f"{ASSET_BASE_URL}/template.png")
        avatar_f = executor.submit(download_image, f"{ASSET_BASE_URL}/characters/{avatar_id}.png")
        template, avatar = template_f.result(), avatar_f.result()

    if not template:
        return Response("Failed to load template", status=500)

    # Apply character customization
    if avatar:
        char_config = CHARACTER_CONFIGS.get(avatar_id, {
            'position': DEFAULT_POSITIONS['character']['position'],
            'size': DEFAULT_POSITIONS['character']['size']
        })
        avatar = avatar.resize(char_config['size'])
        pos = char_config['position']
        template.paste(avatar, (pos[0] - avatar.width // 2, pos[1] - avatar.height // 2), avatar)

    # Process all items
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        
        for category, items in category_items.items():
            for i, item_id in enumerate(items[:len(DEFAULT_POSITIONS[category])]):
                item_config = DEFAULT_POSITIONS[category][i]
                futures.append((
                    executor.submit(download_image, f"{ASSET_BASE_URL}/{CATEGORIES[category]}/{item_id}.png"),
                    category,
                    item_config,
                    item_id
                ))

        for future, category, item_config, item_id in futures:
            img = future.result()
            if img:
                if category == 'weapons':
                    weapon_size = WEAPON_STRETCH['custom'].get(item_id, WEAPON_STRETCH['default'])
                    img = img.resize((weapon_size['width'], weapon_size['height']))
                else:
                    img = img.resize(item_config['size'])
                position = item_config['position']
                template.paste(img, (position[0] - img.width // 2, position[1] - img.height // 2), img)

    # Add player name if provided
    if player_name:
        draw = ImageDraw.Draw(template)
        font = get_font()
        
        # Wrap text if too long
        max_width = DEFAULT_POSITIONS['name']['max_width']
        avg_char_width = font.getlength("A")
        max_chars = int(max_width / avg_char_width)
        
        if font.getlength(player_name) > max_width:
            wrapped_text = textwrap.fill(player_name, width=max_chars)
        else:
            wrapped_text = player_name
        
        # Calculate text position (centered)
        text_bbox = draw.textbbox((0, 0), wrapped_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        x = DEFAULT_POSITIONS['name']['position'][0] - text_width // 2
        y = DEFAULT_POSITIONS['name']['position'][1] - text_height // 2
        
        # Draw text with outline
        draw_text_with_outline(
            draw, (x, y), wrapped_text, font,
            FONT_COLOR, OUTLINE_COLOR, OUTLINE_WIDTH
        )

    print(f"Image generated in {time.time() - start_time:.2f}s")

    output = io.BytesIO()
    template.save(output, "PNG", optimize=True)
    output.seek(0)
    return send_file(output, mimetype="image/png")

if __name__ == "__main__":
    app.run(threaded=True)
