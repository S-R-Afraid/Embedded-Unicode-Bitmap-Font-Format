
# Embedded Unicode Bitmap Font Format (EUBF)
Version 1.2

本规范定义了一种适用于嵌入式系统的 Unicode 位图字库文件格式。  
该格式设计用于在 MCU + 外部存储（SD / USB / SPI Flash）环境中高效显示多语言文本。

典型应用场景：

- 嵌入式 GUI
- LCD / OLED / E-Paper 显示
- 外部存储字体
- 多语言 Unicode UI

设计目标：

- Unicode 全兼容
- O(1) 字符查找
- 支持多字体、多字号
- 支持比例字体（Proportional Font）
- 支持基线排版（Baseline Layout）
- MCU 端实现简单
- 支持未来扩展

---

# 1 术语

|术语|说明|
|---|---|
|Glyph|字符对应的字形|
|Codepoint|Unicode 编码|
|Font Instance|某字体的某一字号|
|Bitmap|字形像素数据|
|Page|256 个 Unicode 字符组成的页|
|Bounding Box|包围字符像素的最小矩形|
|Advance|字符渲染后光标移动距离|
|Baseline|文本排版基准线|

---

# 2 文件结构

EUBF 文件由以下部分组成：

```

+---------------------------+
| Font Header               |
+---------------------------+
| Unicode Page Directory    |
+---------------------------+
| Unicode Page Tables       |
+---------------------------+
| Glyph Offset Table        |
+---------------------------+
| Glyph Data                |
| (Meta + Bitmap)           |
+---------------------------+

````

---

# 3 文件基本属性

|属性|说明|
|---|---|
|编码|Unicode|
|字形|Bitmap|
|字形排列|Row-major|
|位序|MSB-first|
|字节序|Little Endian|
|查找复杂度|O(1)|

---

# 4 Font Header

Font Header 位于文件起始位置。

```c
struct FontHeader
{
    char magic[4];          // "EUBF"

    uint16_t version;       // 版本号 (0x0102 = 1.2)

    char font_name[32];     // 字体名称

    uint16_t font_size;     // 字号 (pixel)

    uint16_t ascent;        // 基线以上最大高度
    uint16_t descent;       // 基线以下最大高度

    uint16_t line_height;   // 推荐行高

    uint16_t max_advance;   // 最大字符步进宽

    uint8_t  bpp;           // bits per pixel (1 / 4 / 8)

    uint16_t max_width;     // 最大包围盒宽
    uint16_t max_height;    // 最大包围盒高

    uint32_t glyph_count;   // 字形总数

    uint16_t missing_glyph; // 缺失字符 glyph id

    uint32_t page_dir_offset;
    uint32_t page_table_offset;
    uint32_t glyph_offset_offset;
    uint32_t glyph_data_offset;

    char source_ttf[64];    // 原始 TTF 文件名

    uint32_t ttf_crc;       // TTF 校验值
};
````

---

# 5 Unicode Page 机制

Unicode 最大值：

```
0x10FFFF
```

将 Unicode 按 **256 字符一页**划分。

计算方法：

```
page_id = unicode >> 8
index   = unicode & 0xFF
```

示例：

```
Unicode: 0x4E2D

page_id = 0x4E
index   = 0x2D
```

---

# 6 Page Directory

Page Directory 为固定长度数组。

Unicode 总页数：

```
0x110000 / 256 = 4352
```

结构：

```
uint32_t page_dir[4352]
```

含义：

```
page_dir[page_id] = page_table_offset
```

若该页不存在：

```
page_dir[page_id] = 0xFFFFFFFF
```

空间占用：

```
4352 × 4 = 17408 bytes
```

---

# 7 Page Table

每个 Page Table 包含 256 个字符入口。

结构：

```
uint16_t glyph_index[256]
```

含义：

```
glyph_index[index] = glyph_id
```

若字符不存在：

```
glyph_index[index] = 0xFFFF
```

Page Table 大小：

```
256 × 2 = 512 bytes
```

---

# 8 Glyph Offset Table

Glyph Offset Table 用于定位字形数据。

结构：

```
uint32_t glyph_offset[glyph_count]
```

含义：

```
glyph_data_address =
glyph_data_base + glyph_offset[glyph_id]
```

支持：

* 变长 bitmap
* 字模压缩
* 可扩展数据

---

# 9 Glyph Data

Glyph Data 区顺序存储所有字形数据。

```
glyph0
glyph1
glyph2
...
```

每个 glyph 数据块由：

```
GlyphMeta + Bitmap
```

组成。

---

# 10 GlyphMeta

每个字符包含一个字形元数据头。

结构：

```c
struct GlyphMeta
{
    uint8_t  box_width;     // 包围盒宽
    uint8_t  box_height;    // 包围盒高

    int8_t   x_offset;      // 绘制 X 偏移
    int8_t   y_offset;      // 绘制 Y 偏移

    uint16_t advance;       // 字符步进宽

    uint16_t reserved;      // 保留 (对齐)
};
```

结构大小：

```
8 bytes
```

说明：

| 字段         | 说明        |
| ---------- | --------- |
| box_width  | 字形宽       |
| box_height | 字形高       |
| x_offset   | 相对光标水平偏移  |
| y_offset   | 相对基线垂直偏移  |
| advance    | 渲染后光标移动距离 |

---

# 11 Bitmap 数据

Bitmap 紧跟在 GlyphMeta 后。

计算方式：

```
bytes_per_row = ceil(box_width × bpp / 8)

bitmap_size =
bytes_per_row × box_height
```

排列规则：

* row-major
* MSB-first
* 每行字节对齐

示例（1bpp）：

```
bit7 = left pixel
bit0 = right pixel
```

---

# 12 字符查找算法

输入：

```
unicode
```

查找流程：

### Step1

```
page_id = unicode >> 8
```

---

### Step2

```
page_offset = page_dir[page_id]
```

若：

```
page_offset == 0xFFFFFFFF
```

使用：

```
missing_glyph
```

---

### Step3

```
index = unicode & 0xFF
glyph_id = page_table[index]
```

若：

```
glyph_id == 0xFFFF
```

使用：

```
missing_glyph
```

---

### Step4

```
glyph_offset =
glyph_offset_table[glyph_id]
```

---

### Step5

读取 GlyphMeta：

```
glyph_address =
glyph_data_base + glyph_offset
```

---

### Step6

计算 bitmap 大小并读取 bitmap。

---

# 13 渲染算法

假设当前光标：

```
cursor_x
cursor_y
```

其中：

```
cursor_y = baseline
```

绘制位置：

```
draw_x = cursor_x + x_offset
draw_y = cursor_y + y_offset
```

绘制：

```
draw_bitmap(
    draw_x,
    draw_y,
    box_width,
    box_height
)
```

更新光标：

```
cursor_x += advance
```

---

# 14 Missing Glyph

若字符不存在：

```
glyph_id = missing_glyph
```

常见 glyph：

```
□
?
```

---

# 15 Kerning

EUBF 不支持 Kerning。

原因：

* Kerning 表巨大
* MCU 查找复杂

嵌入式系统通常仅使用：

```
advance
```

进行排版。

---

# 16 空间估算

示例：

```
字符数 = 3000
平均包围盒 = 16×16
bpp = 1
```

Bitmap：

```
bytes_per_row = 2
bitmap = 32 bytes
```

单 glyph：

```
meta = 8
bitmap = 32
total = 40 bytes
```

Glyph Data：

```
3000 × 40 = 120 KB
```

Offset Table：

```
3000 × 4 = 12 KB
```

Page Tables：

```
40 × 512 = 20 KB
```

Directory：

```
17 KB
```

总计：

```
≈169 KB
```

---

# 17 字库生成流程

推荐生成流程：

```
TTF
 ↓
Python Script
 ↓
FreeType
 ↓
Glyph Render
 ↓
Unicode Page Builder
 ↓
EUBF Writer
```

步骤：

1 扫描字符集
2 FreeType 渲染 glyph
3 计算 GlyphMeta
4 构建 Page Table
5 写入文件结构

---

# 18 字体组织方式

推荐目录结构：

```
fonts/

    Roboto/
        12.eubf
        16.eubf
        24.eubf

    NotoSansCJK/
        16.eubf
        24.eubf
```

每个文件：

```
一个字体
一个字号
```

---

# 19 扩展能力

EUBF 可扩展支持：

* 字模压缩
* Glyph Cache
* 多字体 fallback
* 彩色字体

通过保留字段实现。

---

# 20 总结

EUBF 字库格式特点：

| 特性      | 说明   |
| ------- | ---- |
| Unicode | 完整支持 |
| 查找速度    | O(1) |
| 比例字体    | 支持   |
| 基线排版    | 支持   |
| 实现复杂度   | 低    |
| 外部存储    | 友好   |

该格式适用于需要 **稳定、高效、多语言字体渲染** 的嵌入式系统。

# 21 建议

- 在MCU上使用EUBF字库时，建议使用缓存机制，避免频繁访问外部存储。即建立最近最少使用（LRU）缓存，将常用 glyph 缓存到内存中。缓存区大小视该芯片内存大小而定，建议足够存储100个glyph。
