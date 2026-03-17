import struct
import os

# ================= 配置区 =================
FILE_PATH = "asset\\fount\\myfont\\16.eubf"
#将要检查的字库地址填在上面。

# =========================================

def analyze_eubf_robust(path):
    if not os.path.exists(path):
        print(f"错误: 找不到文件 {path}")
        return

    file_size = os.path.getsize(path)
    print(f"--- 文件系统检查 ---")
    print(f"文件路径: {path}")
    print(f"实际文件大小: {file_size} 字节")

    with open(path, 'rb') as f:
        data = f.read()

    # 1. 解析 Header (146 字节)
    try:
        header_fmt = '<4sH32sHHHHHBxHH I H H I I I I 64s I'
        header = struct.unpack('<4sH32sHHHHHBxHH I H H I I I I 64s I', data[:146])
    except Exception as e:
        print(f"Header 解析失败: {e}")
        return

    magic = header[0].decode('ascii', errors='ignore')
    font_name = header[2].split(b'\x00')[0].decode('utf-8', errors='ignore')
    glyph_count = header[12]
    pg_dir_off = header[14]

    print(f"\n--- Header 信息 ---")
    print(f"Magic: {magic} | 字体: {font_name} | 总字数: {glyph_count}")
    print(f"Page Directory 偏移: {pg_dir_off}")

    # 2. 扫描索引
    if pg_dir_off + 1024 > file_size:
        print(f"致命错误: Page Directory 偏移量已超出文件范围!")
        return

    page_dir = struct.unpack('<256I', data[pg_dir_off: pg_dir_off + 1024])

    found_pages = 0
    for page_id, page_offset in enumerate(page_dir):
        if page_offset != 0xFFFFFFFF:
            found_pages += 1
            # 【关键检查】：检查偏移量是否越界
            if page_offset + 512 > file_size:
                print(f"警告: Page {page_id} 偏移量(0x{page_offset:X})指向文件外部! (文件仅 {file_size} 字节)")
                continue

            page_table = struct.unpack('<256H', data[page_offset: page_offset + 512])
            for char_idx, glyph_id in enumerate(page_table):
                if glyph_id != 0xFFFF:
                    uni = (page_id << 8) | char_idx
                    print(f"发现字符: U+{uni:04X} ({chr(uni) if uni < 0xFFFF else '?'}) -> GID: {glyph_id}")

    if found_pages == 0:
        print("提示: 索引表为空，文件中可能没有定义任何字符。")


if __name__ == "__main__":
    analyze_eubf_robust(FILE_PATH)
