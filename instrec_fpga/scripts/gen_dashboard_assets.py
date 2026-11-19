"""Freeze the dashboard's Chinese glyphs and tile map for synchronous RTL ROMs."""
from pathlib import Path
import hashlib
import json
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'src/ui'
CLASSES = ['单簧管', '失真电吉他', '女声', '长笛', '钢琴', '次中音萨克斯', '小号', '小提琴', '等待识别']
ENGLISH = ['clarinet', 'distorted electric guitar', 'female singer', 'flute', 'piano', 'tenor saxophone', 'trumpet', 'violin']


def generate(demo=None):
    global OUT, CLASSES
    if demo is not None:
        CLASSES = demo["classes_zh"] + ["等待播放"]
    assert demo is not None or json.loads((ROOT / 'scripts/outputs/layer_contract.json').read_text(encoding='utf-8'))['classes']['names'] == ENGLISH
    font_path = Path('C:/Windows/Fonts/msyh.ttc')
    ascii_path = Path('C:/Windows/Fonts/consola.ttf')
    chinese = ImageFont.truetype(str(font_path), 27)
    ascii_font = ImageFont.truetype(str(ascii_path), 26)
    glyphs = [[0] * 32]
    lookup = {}
    tiles = [0] * 8192
    page_offset = 0
    texts = []

    def chunks(char):
        if char not in lookup:
            width = 16 if ord(char) < 128 else 32
            im = Image.new('1', (width, 32))
            d = ImageDraw.Draw(im)
            font = ascii_font if width == 16 else chinese
            box = d.textbbox((0, 0), char, font=font)
            d.text(((width - (box[2]-box[0]))//2-box[0], (32-(box[3]-box[1]))//2-box[1]), char, font=font, fill=1)
            ids = []
            for offset in range(0, width, 16):
                ids.append(len(glyphs))
                glyphs.append([sum(int(im.getpixel((offset+x, y)) != 0) << (15-x) for x in range(16)) for y in range(32)])
            lookup[char] = ids
        return lookup[char]

    def put(x, y, text, color=1, mode=0):
        assert x % 16 == 0 and y % 32 == 0
        texts.append(dict(x=x, y=y, text=text, mode=mode))
        col = x//16
        for c in text:
            for token in chunks(c):
                addr = page_offset+y//32*120+col
                assert tiles[addr] == 0, (text, addr)
                tiles[addr] = color << 12 | mode << 8 | token
                col += 1

    for page in range(2):
        page_offset = page*4096
        put(32, 64, '乐境', 5)
        put(32, 192, '实时', 5 if page == 0 else 6)
        put(32, 288, '记录', 5 if page == 1 else 6)
        put(256, 64, '聆听' if page == 0 else '结果与收藏', 1)
        put(1408, 64, 'INSTREC', 2)
        put(1408, 192, '当前' if page == 0 else '回看', 2)
        tiles[page_offset+6*120+112] = 0x1e00
        if page == 1:
            for digit in range(2):
                tiles[page_offset+6*120+72+digit] = 0x2c00 | digit
            put(1184, 192, '/64', 2)
        put(1408, 352, '置信度', 2)
        for i, label in enumerate(CLASSES[:8]):
            put(1408, 448+64*i, label, 1)
        for y in range(8, 10):
            for x in range(88, 116):
                tiles[page_offset+y*120+x] = 0x3100 | ((x-88)//2)
        for slot in range(9):
            x, y = (1616, 352) if slot == 8 else (1760, 448+64*slot)
            for digit in range(4):
                tiles[page_offset+y//32*120+x//16+digit] = 0x1200 | (slot<<4) | digit
        put(256, 1024, 'K1 页面 / 长按收藏    K2 清空    K3 <    K4 >', 2)
        if page == 0:
            put(256, 192, '声音', 1)
            put(256, 480, '3s', 2)
            put(256, 576, '最近八次', 1)
            put(1200, 640, '最新', 2)
            put(640, 352, '等待音频', 2, 4)
            for i, label in enumerate(['单簧管', '电吉他', '女声', '长笛', '钢琴', '萨克斯', '小号', '小提琴']):
                put(288 + (i % 4) * 256, 928 + (i // 4) * 32, label, 2)
        else:
            put(256, 192, '会话记录', 1)
            put(288, 256, '序号', 2)
            put(448, 256, '时间', 2)
            put(640, 256, '乐器', 2)
            put(1088, 256, '置信度', 2)
            for row in range(8):
                y = 320 + row*64
                for mode, x, width in [(7,640,12),(8,288,4),(9,432,5),(10,1088,4),(11,1248,1)]:
                    for col in range(width):
                        tiles[page_offset+y//32*120+x//16+col] = 0x1000 | mode<<8 | row<<4 | col
            put(640, 896, '暂无记录', 2, 13)
    for c in '0123456789-% :*':
        chunks(c)
    ascii_ids = [lookup.get(chr(i), [0])[0] for i in range(128)]
    class_ids = []
    for label in CLASSES:
        ids = [n for c in label for n in chunks(c)]
        class_ids.extend(ids + [0]*(16-len(ids)))
    assert len(glyphs) <= 256, len(glyphs)
    glyphs.extend([[0]*32 for _ in range(256-len(glyphs))])
    class_ids.extend([0]*(256-len(class_ids)))

    def write(name, values, width):
        (OUT / (("demo_" if demo else "") + name)).write_text(''.join(f'{v:0{width}x}\n' for v in values), encoding='ascii')
    write('dashboard_font.hex', [v for g in glyphs for v in g], 4)
    write('dashboard_tiles.hex', tiles, 4)
    write('dashboard_ascii.hex', ascii_ids, 2)
    write('dashboard_classes.hex', class_ids, 2)
    metadata = dict(classes=CLASSES, texts=texts, glyph_chunks=len(lookup), font_sha256=hashlib.sha256(font_path.read_bytes()).hexdigest(), ascii_sha256=hashlib.sha256(ascii_path.read_bytes()).hexdigest())
    (OUT / ('demo_dashboard_assets.json' if demo else 'dashboard_assets.json')).write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Dashboard ROM assets generated:', len(lookup), 'characters')


if __name__ == '__main__':
    generate()
