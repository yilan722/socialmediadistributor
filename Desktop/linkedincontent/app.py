import streamlit as st
import requests
import pdfplumber
import io
import time
import textwrap
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

# --- 全局配置 ---
st.set_page_config(page_title="Pro Research Agent (Visual Edition)", layout="wide", page_icon="💎")

# 配置绘图风格 (解决中文乱码和样式问题)
plt.style.use('ggplot')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial', 'DejaVu Sans', 'Microsoft YaHei'] 
plt.rcParams['axes.unicode_minus'] = False

# --- 状态管理 ---
if 'history' not in st.session_state:
    st.session_state['history'] = []
if 'current_report' not in st.session_state:
    st.session_state['current_report'] = None

# --- 核心功能函数 ---

def extract_pages_from_pdf(uploaded_file):
    """按页提取文本，保证上下文完整"""
    pages_content = []
    with pdfplumber.open(uploaded_file) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                pages_content.append(text)
    return pages_content

def call_ai_api(api_key, base_url, model_name, messages, temperature=0.1):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model_name, "messages": messages, "temperature": temperature, "stream": False}
    try:
        response = requests.post(base_url, headers=headers, json=payload, timeout=300)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            print(f"⚠️ API Error: {response.status_code}")
            return None 
    except Exception as e:
        print(f"⚠️ Connection Error: {e}")
        return None

def create_professional_table_image(markdown_table_lines):
    """
    【高容错表格绘图引擎】
    将 Markdown 表格文本转化为 Matplotlib 图片对象 (BytesIO)
    """
    try:
        # 1. 预处理：清洗数据
        clean_rows = []
        for line in markdown_table_lines:
            content = line.strip()
            # 必须包含 | 且不仅仅是分割线
            if '|' in content:
                # 移除 Markdown 的分割线行 (例如 |---|---|)
                clean_check = content.replace('|', '').replace('-', '').replace(':', '').strip()
                if clean_check: 
                    clean_rows.append(content)
        
        if len(clean_rows) < 2: return None # 至少要有表头和一行数据
        
        # 2. 智能解析：按 | 分割
        data_matrix = []
        max_cols = 0
        
        for line in clean_rows:
            # 移除首尾可能多余的 |
            line_pure = line.strip()
            if line_pure.startswith('|'): line_pure = line_pure[1:]
            if line_pure.endswith('|'): line_pure = line_pure[:-1]
            
            cells = [c.strip() for c in line_pure.split('|')]
            data_matrix.append(cells)
            if len(cells) > max_cols: max_cols = len(cells)

        # 3. 补齐列数（防止不规则表格报错）
        final_data = []
        for row in data_matrix:
            if len(row) < max_cols:
                row += [""] * (max_cols - len(row))
            final_data.append(row[:max_cols])
            
        if not final_data: return None

        # 4. 转换为 DataFrame
        headers = final_data[0]
        body = final_data[1:]
        if not body: body = [[""] * len(headers)] # 防止只有表头
        
        df = pd.DataFrame(body, columns=headers)

        # 5. 绘图计算
        # 动态计算高度：根据内容字数决定行高
        row_heights = []
        col_width_chars = 20
        for row in body:
            max_lines = 1
            for cell in row:
                # 粗略估算换行行数
                lines = len(textwrap.wrap(str(cell), width=col_width_chars))
                if lines > max_lines: max_lines = lines
            row_heights.append(max_lines)
            
        base_h = 0.5
        total_h = 0.8 + sum([rh * base_h for rh in row_heights]) # 表头 + 内容
        total_w = min(len(headers) * 3.0, 12) # 宽度自适应

        fig, ax = plt.subplots(figsize=(total_w, total_h))
        ax.axis('off')
        
        # 绘制表格
        table = ax.table(cellText=df.values, colLabels=df.columns, loc='center', cellLoc='left')
        
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        
        # 样式美化
        cells = table.get_celld()
        for (row, col), cell in cells.items():
            cell.set_edgecolor('#bfbfbf')
            cell.set_linewidth(1)
            # 设置内边距
            cell.set_text_props(position=(0.02, cell.get_text_props()['position'][1])) 
            
            if row == 0:
                cell.set_height(0.8 / total_h)
                cell.set_facecolor('#2c3e50') # 深蓝色表头
                cell.set_text_props(color='white', weight='bold', ha='center', fontsize=12)
            else:
                rh_mult = row_heights[row-1]
                cell.set_height((rh_mult * base_h) / total_h)
                cell.set_facecolor('#f8f9fa' if row % 2 else '#ffffff') # 斑马纹
                cell.set_text_props(color='#333333', wrap=True, ha='left', va='center')

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', bbox_inches='tight', dpi=300, pad_inches=0.1)
        plt.close(fig)
        img_buffer.seek(0)
        return img_buffer

    except Exception as e:
        print(f"Table Gen Error: {e}")
        return None

def parse_content_with_images(text_content):
    """
    【核心转换器】
    将纯文本拆分为结构化列表：[TextBlock, ImageBlock, TextBlock...]
    这解决了 UI 和 Word 无法同时渲染图文的问题。
    """
    lines = text_content.split('\n')
    parsed_blocks = [] # List of {'type': 'text'/'image', 'content': str/bytes}
    
    current_text_buffer = []
    table_buffer = []
    inside_table = False
    
    for line in lines:
        stripped = line.strip()
        # 判定表格行：包含竖线，且长度大于3（排除干扰字符）
        is_potential_table_row = '|' in stripped and len(stripped) > 3
        
        if is_potential_table_row:
            if not inside_table:
                # 刚进入表格，先把之前的文本存入 Block
                if current_text_buffer:
                    parsed_blocks.append({'type': 'text', 'content': "\n".join(current_text_buffer)})
                    current_text_buffer = []
                inside_table = True
            table_buffer.append(stripped)
        else:
            if inside_table:
                # 表格结束，立即生成图片 Block
                img_bytes = create_professional_table_image(table_buffer)
                if img_bytes:
                    parsed_blocks.append({'type': 'image', 'content': img_bytes})
                else:
                    # 如果生成失败（比如不是真表格），回退为文本
                    current_text_buffer.extend(table_buffer)
                
                inside_table = False
                table_buffer = []
                
            current_text_buffer.append(line)
            
    # 处理文档末尾的残留
    if inside_table and table_buffer:
        img_bytes = create_professional_table_image(table_buffer)
        if img_bytes:
            parsed_blocks.append({'type': 'image', 'content': img_bytes})
        else:
            current_text_buffer.extend(table_buffer)
            
    if current_text_buffer:
        parsed_blocks.append({'type': 'text', 'content': "\n".join(current_text_buffer)})
        
    return parsed_blocks

def generate_mixed_word(parsed_blocks):
    """
    根据 Block 列表生成 Word，确保图文混排
    """
    doc = Document()
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimHei')
    
    # 头部
    doc.add_heading('Investment Research Report', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"Generated by AI | {datetime.now().strftime('%Y-%m-%d')}", style='Normal').alignment = WD_ALIGN_PARAGRAPH.RIGHT
    doc.add_paragraph("_" * 50)

    for block in parsed_blocks:
        if block['type'] == 'text':
            # 处理文本中的标题格式
            for line in block['content'].split('\n'):
                s_line = line.strip()
                if not s_line: continue
                if s_line.startswith('# '): doc.add_heading(s_line[2:], 1)
                elif s_line.startswith('## '): doc.add_heading(s_line[3:], 2)
                elif s_line.startswith('### '): doc.add_heading(s_line[4:], 3)
                elif s_line.startswith('- ') or s_line.startswith('* '): doc.add_paragraph(s_line[2:], style='List Bullet')
                else: doc.add_paragraph(s_line)
                
        elif block['type'] == 'image':
            # 插入图片
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run()
            try:
                block['content'].seek(0)
                run.add_picture(block['content'], width=Inches(6.2))
            except Exception:
                p.add_run("[Image Generation Error]")

    bio = io.BytesIO()
    doc.save(bio)
    return bio

# --- UI 侧边栏 ---
with st.sidebar:
    st.title("🗃️ 历史记录")
    if st.session_state['history']:
        for i, item in enumerate(reversed(st.session_state['history'])):
            if st.button(f"Load: {item['time']}", key=f"hist_{i}"):
                st.session_state['current_report'] = item
                st.rerun()
    st.divider()
    api_key = st.text_input("API Key", value="sk-3UIO8MwTblfyQuEZz2WUCzQOuK4QwwIPALVcNxFFNUxJayu7", type="password")
    model_name = st.selectbox("Model", ["gemini-3-pro", "gpt-4o", "qwen-max"])

# --- 主界面 ---
st.title("💎 Pro Research Agent (Visual & Word Perfect)")

uploaded_file = st.file_uploader("上传 PDF 资料", type=['pdf'])

if uploaded_file and st.button("🔥 开始完美转化"):
    api_url = "https://api.nuwaapi.com/v1/chat/completions"
    
    # 1. 解析 PDF
    with st.spinner("📖 逐页读取 PDF..."):
        pages_list = extract_pages_from_pdf(uploaded_file)

    # 2. 1:1 数字化 (Markdown)
    full_text_parts = []
    progress_bar = st.progress(0)
    
    for i, page_text in enumerate(pages_list):
        # OCR 级 Prompt
        prompt = """
        You are an OCR Engine. Goal: EXACT COPY.
        Rules:
        1. Output TEXT exactly as seen (Word-for-Word).
        2. Detect TABLES and format them as Markdown Tables (| Header |... |---|). 
           - DO NOT OMIT DATA. 
           - KEEP EVERY ROW.
        3. No summaries. No intro/outro text.
        """
        msg = [{"role": "user", "content": f"{prompt}\n\nCONTENT:\n{page_text}"}]
        res = call_ai_api(api_key, api_url, model_name, msg)
        
        if res: full_text_parts.append(res)
        else: full_text_parts.append(page_text) # Fallback
        
        progress_bar.progress((i + 1) / len(pages_list))

    full_article = "\n\n".join(full_text_parts)

    # 3. 预处理 (生成图片对象) - 关键步骤
    with st.spinner("🎨 正在渲染表格图片与可视化视图..."):
        # 将文本转为 [Text, Image, Text] 的结构
        parsed_blocks = parse_content_with_images(full_article)

    # 4. 社媒生成
    with st.spinner("🧠 撰写社媒文案 (Lead Analyst)..."):
        social_prompt = """
        Act as a Lead Analyst. Write social media content (LinkedIn, Twitter, Reddit) based on this report.
        Focus on: Logic, Catalysts, and Upside.
        """
        msg_social = [{"role": "user", "content": f"{social_prompt}\n\nREPORT:\n{full_article[:8000]}"}]
        social_res = call_ai_api(api_key, api_url, model_name, msg_social, temperature=0.7)

    # 5. 生成 Word
    word_bio = generate_mixed_word(parsed_blocks)

    # 6. 存档
    report_data = {
        "time": datetime.now().strftime("%H:%M"),
        "filename": uploaded_file.name,
        "blocks": parsed_blocks, # 存 blocks 用于渲染
        "social": social_res,
        "word_data": word_bio.getvalue()
    }
    st.session_state['current_report'] = report_data
    st.session_state['history'].append(report_data)
    st.rerun()

# --- 结果展示 ---
current = st.session_state['current_report']

if current:
    st.divider()
    st.markdown(f"## 📊 交付: {current['filename']}")
    
    col1, col2 = st.columns([6, 4])
    
    # === 左侧：图文可视化报告 ===
    with col1:
        st.subheader("📄 1:1 可视化报告 (图文还原)")
        st.download_button(
            "💾 下载 Word 报告 (含表格图片)",
            data=current['word_data'],
            file_name=f"Report_{current['time']}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        st.markdown("---")
        
        # 使用容器循环渲染 Block
        container = st.container(height=800, border=True)
        with container:
            if 'blocks' in current:
                for block in current['blocks']:
                    if block['type'] == 'text':
                        st.markdown(block['content'])
                    elif block['type'] == 'image':
                        # 直接显示图片！
                        block['content'].seek(0)
                        st.image(block['content'], use_container_width=True)

    # === 右侧：社媒文案 ===
    with col2:
        st.subheader("🔥 深度社媒文案")
        st.text_area("Social Media Copy", value=current.get('social', ''), height=800)

elif not uploaded_file:
    st.info("👈 请上传 PDF。系统将生成【包含真实表格图片】的 Word 报告，并在网页左侧直接显示图文效果。")
