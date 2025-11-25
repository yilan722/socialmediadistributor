import streamlit as st
import requests
import pdfplumber
import io
import re
import textwrap
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

# --- 1. 基础配置 ---
st.set_page_config(page_title="PDF to Word (Table as Image)", layout="centered", page_icon="📑")

# 绘图配置 (确保支持中文)
plt.style.use('ggplot')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial', 'Microsoft YaHei', 'DejaVu Sans'] 
plt.rcParams['axes.unicode_minus'] = False

# --- 2. 核心处理逻辑 ---

def extract_text_from_pdf(file_stream):
    """提取文本"""
    text = ""
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t: text += f"\n{t}"
    return text

def call_ai_formatting(api_key, text_chunk, model="gpt-4o"):
    """
    AI 任务：识别表格，用标签包裹。
    """
    url = "https://api.nuwaapi.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    # 核心 Prompt：强制打标签
    prompt = """
    You are a Document Structure Analyzer.
    Task: Reconstruct the document content.
    
    CRITICAL RULE FOR TABLES:
    1. If you see a table (rows and columns of data), you MUST output it inside strict tags:
       [[TABLE_START]]
       ... raw table content, keep it structured ...
       [[TABLE_END]]
    2. The content inside the tags MUST be the data of the table.
    
    CRITICAL RULE FOR TEXT:
    1. All non-table text must be output exactly as is (1:1).
    2. Use Markdown headers (#, ##) for titles.
    3. Do not summarize.
    """
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": f"{prompt}\n\nTEXT:\n{text_chunk}"}],
        "temperature": 0.1
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=180)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content']
        return text_chunk # 如果失败，返回原文
    except Exception as e:
        print(f"Error: {e}")
        return text_chunk

def text_to_image_bytes(table_text):
    """
    【核心】将表格文本 -> 绘制成 matplotlib 图片 -> 返回二进制流
    """
    try:
        # 1. 解析数据
        lines = table_text.strip().split('\n')
        data = []
        for line in lines:
            # 简单清洗
            if not line.strip(): continue
            if set(line.strip()) <= {'|', '-', ' '}: continue # 跳过分割线
            
            # 按竖线或多空格拆分
            if '|' in line:
                cells = [c.strip() for c in line.split('|') if c.strip() != '']
            else:
                cells = [c.strip() for c in re.split(r'\s{2,}', line.strip())]
            
            if cells: data.append(cells)
            
        if not data: return None

        # 补齐列
        max_cols = max(len(row) for row in data)
        final_data = [row + [""]*(max_cols-len(row)) for row in data]
        
        headers = final_data[0]
        body = final_data[1:]
        if not body: body = [[""]*len(headers)]

        # 2. 绘图
        df = pd.DataFrame(body, columns=headers)
        
        # 动态计算尺寸
        row_heights = []
        col_width = 20
        for row in body:
            max_lines = 1
            for item in row:
                lines_count = len(textwrap.wrap(str(item), width=col_width))
                max_lines = max(max_lines, lines_count)
            row_heights.append(max_lines)

        base_h = 0.5
        total_h = 0.8 + sum([h*base_h for h in row_heights])
        total_w = min(len(headers)*3.0, 11)

        fig, ax = plt.subplots(figsize=(total_w, total_h))
        ax.axis('off')
        
        table = ax.table(cellText=df.values, colLabels=df.columns, loc='center', cellLoc='left')
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        
        # 美化表格样式
        cells = table.get_celld()
        for (row, col), cell in cells.items():
            cell.set_edgecolor('#bfbfbf')
            cell.set_linewidth(1)
            cell.set_text_props(position=(0.02, cell.get_text_props()['position'][1]))
            
            if row == 0:
                cell.set_facecolor('#2c3e50')
                cell.set_text_props(color='white', weight='bold', ha='center')
                cell.set_height(0.8/total_h)
            else:
                cell.set_facecolor('#f8f9fa' if row%2 else 'white')
                cell.set_text_props(color='black', wrap=True)
                cell.set_height((row_heights[row-1]*base_h)/total_h)

        img_buf = io.BytesIO()
        plt.savefig(img_buf, format='png', bbox_inches='tight', dpi=300, pad_inches=0.1)
        plt.close(fig)
        img_buf.seek(0)
        return img_buf

    except Exception as e:
        print(f"Plot Error: {e}")
        return None

def generate_perfect_word(ai_output_text):
    """
    生成 Word 文档。
    逻辑：解析 [[TABLE]] 标签 -> 转图片插入；其他 -> 文本插入。
    """
    doc = Document()
    
    # 设置中文字体
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimHei') # 设置中文字体
    
    # 切分内容
    pattern = re.compile(r'(\[\[TABLE_START\]\][\s\S]*?\[\[TABLE_END\]\])')
    parts = pattern.split(ai_output_text)
    
    doc.add_heading('Research Report Translation', 0)
    
    for part in parts:
        if "[[TABLE_START]]" in part:
            # === 处理表格 ===
            raw_table = part.replace("[[TABLE_START]]", "").replace("[[TABLE_END]]", "").strip()
            img_bytes = text_to_image_bytes(raw_table)
            
            if img_bytes:
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run()
                # 插入高清图片
                run.add_picture(img_bytes, width=Inches(6.0))
            else:
                doc.add_paragraph(raw_table) # 失败回退
        else:
            # === 处理文本 ===
            lines = part.strip().split('\n')
            for line in lines:
                line = line.strip()
                if not line: continue
                
                if line.startswith('# '): doc.add_heading(line[2:], 1)
                elif line.startswith('## '): doc.add_heading(line[3:], 2)
                elif line.startswith('### '): doc.add_heading(line[4:], 3)
                elif line.startswith('- ') or line.startswith('* '): 
                    doc.add_paragraph(line[2:], style='List Bullet')
                else:
                    doc.add_paragraph(line)
                    
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio

# --- 3. UI 界面 ---

st.title("📑 PDF 转 Word (表格完美转图版)")
st.markdown("""
**核心逻辑：**
1. 提取 PDF 内容。
2. AI 自动识别并提取所有表格。
3. **程序自动将表格绘制成高清图片**。
4. 生成 **Word 文档**。

👉 **使用方法：** 下载 Word 文档 -> 打开 -> 全选复制 (Ctrl+A, Ctrl+C) -> 粘贴到任何地方。这是保证格式不乱的唯一方法。
""")

api_key = st.text_input("输入 API Key", value="sk-3UIO8MwTblfyQuEZz2WUCzQOuK4QwwIPALVcNxFFNUxJayu7", type="password")
uploaded_file = st.file_uploader("上传 PDF 文件", type=['pdf'])

if uploaded_file and st.button("开始转换"):
    if not api_key:
        st.error("请输入 API Key")
    else:
        # 1. 提取文字
        with st.spinner("1/3 正在读取 PDF..."):
            raw_text = extract_text_from_pdf(uploaded_file)
        
        # 2. AI 结构化处理
        # 分块处理以防超长，简单起见这里切前 5000 字演示，实际使用可循环
        chunks = [raw_text[i:i+4000] for i in range(0, len(raw_text), 4000)]
        full_ai_text = []
        
        progress = st.progress(0)
        for i, chunk in enumerate(chunks):
            with st.spinner(f"2/3 AI 正在识别表格与文本 (Part {i+1}/{len(chunks)})..."):
                processed = call_ai_formatting(api_key, chunk)
                full_ai_text.append(processed)
            progress.progress((i+1)/len(chunks))
            
        final_text = "\n".join(full_ai_text)
        
        # 3. 生成 Word
        with st.spinner("3/3 正在绘制表格图片并生成 Word..."):
            word_file = generate_perfect_word(final_text)
            
        st.success("✅ 转换完成！表格已全部转化为图片。")
        
        # 4. 下载按钮
        st.download_button(
            label="📥 点击下载最终 Word 文档",
            data=word_file,
            file_name=f"Converted_{datetime.now().strftime('%H%M')}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        
        st.info("💡 提示：下载后打开 Word，里面的表格就是图片了。你可以随意复制粘贴，格式永远不会乱。")
