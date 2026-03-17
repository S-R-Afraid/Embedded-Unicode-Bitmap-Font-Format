import os
import sys
import struct
import zlib
import freetype
import glob
import tempfile
import shutil
import uuid
import re
# ===========================================
#将要打包的字体放在同目录下的needfont文件夹里，然后运行打包脚本即可。
#您还可以传入 -whitelist 参数来读取whitelist.txt里的字符来按需生成。
#生成的字库放在同目录下的asset/font/<fontname>/里。
#生成完毕后，可运行检查脚本来检查字库是否正确。

#由于读取文件时不分大小，目前这个脚本会把同一个字库生成两遍，算是一个bug，但是不影响使用。
# ================= 全局配置 =================
TARGET_SIZES = [12, 16, 19, 25, 32]
BPP = 4
HEADER_SIZE = 146  # 严格匹配 C 语言 #pragma pack(1)


# ============================================

def get_whitelist_chars():
    whitelist_path = "whitelist.txt"
    chars = set()
    if os.path.exists(whitelist_path):
        with open(whitelist_path, 'r', encoding='utf-8') as f:
            chars = set(f.read())
        print(f"已加载 whitelist.txt，共包含 {len(chars)} 个字符。")
    else:
        print("警告: 未找到 whitelist.txt，将仅生成基础字符。")
    chars.add(' ')
    chars.add('?')
    return chars


def pack_4bpp_bitmap(bitmap, box_w, box_h):
    pitch = bitmap.pitch
    buffer = bitmap.buffer
    bytes_per_row = (box_w + 1) // 2
    packed_data = bytearray()
    for y in range(box_h):
        row_data = buffer[y * pitch: y * pitch + box_w]
        packed_row = bytearray(bytes_per_row)
        for x in range(box_w):
            val = row_data[x] >> 4
            if x % 2 == 0:
                packed_row[x // 2] |= (val << 4)
            else:
                packed_row[x // 2] |= val
        packed_data.extend(packed_row)
    return packed_data


def build_eubf_for_size(face, ttf_path, font_name, size, valid_chars, output_path):
    face.set_pixel_sizes(size, size)
    ascent, descent = face.size.ascender // 64, abs(face.size.descender // 64)
    line_height, max_advance = face.size.height // 64, face.size.max_advance // 64

    glyph_data_block, glyph_offsets, page_tables = bytearray(), [], {}
    max_w, max_h, missing_glyph_id = 0, 0, 0

    print(f"  正在渲染 {size}px 字号...")

    for glyph_id, charcode in enumerate(valid_chars):
        if charcode == ord('?'): missing_glyph_id = glyph_id
        page_id, index = (charcode >> 8) & 0xFF, charcode & 0xFF
        if page_id not in page_tables: page_tables[page_id] = {}
        page_tables[page_id][index] = glyph_id

        face.load_char(charcode, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_NORMAL)
        bitmap = face.glyph.bitmap
        w, h = bitmap.width, bitmap.rows
        max_w, max_h = max(max_w, w), max(max_h, h)

        glyph_offsets.append(len(glyph_data_block))
        meta = struct.pack('<BBbbHH', w, h, face.glyph.bitmap_left, -face.glyph.bitmap_top, face.glyph.advance.x // 64,
                           0)
        glyph_data_block.extend(meta)
        if w > 0 and h > 0:
            glyph_data_block.extend(pack_4bpp_bitmap(bitmap, w, h))

    # 构建索引
    page_dir_offset = HEADER_SIZE
    page_dir_data = bytearray([0xFF] * (256 * 4))
    page_table_offset = page_dir_offset + 1024
    page_tables_data, current_table_ptr = bytearray(), page_table_offset

    for page_id in range(256):
        if page_id in page_tables:
            struct.pack_into('<I', page_dir_data, page_id * 4, current_table_ptr)
            table = bytearray([0xFF] * 512)
            for index, gid in page_tables[page_id].items():
                struct.pack_into('<H', table, index * 2, gid)
            page_tables_data.extend(table)
            current_table_ptr += 512

    glyph_offset_offset = current_table_ptr
    glyph_offset_data = bytearray()
    for offset in glyph_offsets: glyph_offset_data.extend(struct.pack('<I', offset))
    glyph_data_offset = glyph_offset_offset + len(glyph_offset_data)

    # 计算源文件 CRC
    with open(ttf_path, 'rb') as f:
        ttf_crc = zlib.crc32(f.read()) & 0xFFFFFFFF

    name_bytes = font_name.encode('utf-8')[:32]
    ttf_filename = os.path.basename(ttf_path).encode('utf-8')[:64]

    header = struct.pack('<4sH32sHHHHHBxHH I H H I I I I 64s I',
                        b'EUBF', 0x0102, name_bytes, size, ascent, descent, line_height, max_advance, BPP,
                        max_w, max_h, len(valid_chars), missing_glyph_id, 0,
                        page_dir_offset, page_table_offset, glyph_offset_offset, glyph_data_offset,
                        ttf_filename, ttf_crc)

    with open(output_path, 'wb') as f:
        for b in [header, page_dir_data, page_tables_data, glyph_offset_data, glyph_data_block]: f.write(b)
    print(f"    -> 生成完毕: {output_path}")


def main():
    input_dir = "needfont"
    mode = "full" if len(sys.argv) < 2 else sys.argv[1]
    if not os.path.exists(input_dir):
        os.makedirs(input_dir)
        print(f"提示: 已创建 '{input_dir}' 文件夹，请放入字体后再运行。")
        return

    font_files = []
    for ext in ('*.ttf', '*.otf', '*.TTF', '*.OTF'):
        font_files.extend(glob.glob(os.path.join(input_dir, ext)))

    if not font_files:
        print(f"错误: '{input_dir}' 内无字体文件。")
        return

    target_chars = get_whitelist_chars() if mode == "whitelist" else set()
    temp_dir = tempfile.gettempdir()

    for ttf_path in font_files:
        # --- 核心修复：将中文路径文件复制到纯英文临时路径 ---
        _, ext = os.path.splitext(ttf_path)
        temp_ttf = os.path.join(temp_dir, f"eubf_tmp_{uuid.uuid4().hex}{ext}")

        try:
            shutil.copy2(ttf_path, temp_ttf)
            face = freetype.Face(temp_ttf)

            # 提取名称，防止 Windows 路径非法字符
            raw_name = face.family_name.decode('utf-8', errors='ignore') if face.family_name else ""
            font_name = re.sub(r'[\\/*?:"<>|]', '', raw_name).strip() or "font"
            output_dir = os.path.join("asset", "font", font_name)
            os.makedirs(output_dir, exist_ok=True)

            print(f"处理字体: {font_name}...")

            valid_chars = []
            if mode == "whitelist":
                for char in target_chars:
                    if face.get_char_index(ord(char)): valid_chars.append(ord(char))
            else:
                charcode, gindex = face.get_first_char()
                while gindex:
                    valid_chars.append(charcode);
                    charcode, gindex = face.get_next_char(charcode, gindex)

            valid_chars = sorted(list(set(valid_chars)))
            for size in TARGET_SIZES:
                build_eubf_for_size(face, ttf_path, font_name, size, valid_chars,
                                    os.path.join(output_dir, f"{size}.eubf"))

            del face  # 必须先释放句柄才能删除临时文件
        except Exception as e:
            print(f"失败 {ttf_path}: {e}")
        finally:
            if os.path.exists(temp_ttf): os.remove(temp_ttf)

    print("\n🎉 全部打包完成！")


if __name__ == "__main__":
    main()
