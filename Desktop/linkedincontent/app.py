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
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn

# --- 全局配置 ---
st.set_page_config(page_title="Pro Research Agent (Final)", layout="wide", page_icon="💎")

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
    """按页提取文本，保证表格结构不被切分"""
    pages_content = []
    with pdfplumber.open(uploaded_file) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                pages_content.append(text)
    return pages_content

def call_ai_api(api_key, base_url, model_name, messages, temperature=0.1, timeout=300):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model_name, "messages": messages, "temperature": temperature, "stream": False}
    try:
        response = requests.post(base_url, headers=headers, json=payload, timeout=timeout)
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
    【修复版】表格绘图引擎：更强的容错性，确保输出图片
    """
    try:
        # 1. 清洗数据，去除无关的分割线 (如 |---|)
        clean_rows = []
        for line in markdown_table_lines:
            content = line.strip()
            if not content: continue
            # 移除 Markdown 表格的分割行 (包含大量 - 或 :)
            if set(content.replace('|', '').strip()) <= {'-', ':', ' '}:
                continue
            clean_rows.append(content)

        if len(clean_rows) < 2: return None # 至少要有表头和一行数据
        
        # 2. 解析表头
        headers = [h.strip() for h in clean_rows[0].strip('|').split('|')]
        
        # 3. 解析数据行
        data = []
        row_heights = []
        col_width_chars = 20 # 稍微调小换行宽度，防止图片过高
        
        for row_line in clean_rows[1:]:
            cells = [c.strip() for c in row_line.strip('|').split('|')]
            
            # 对齐列数 (不足补空，多了截断)
            if len(cells) < len(headers):
                cells += [""] * (len(headers) - len(cells))
            elif len(cells) > len(headers):
                cells = cells[:len(headers)]
                
            wrapped_row = []
            max_lines = 1
            for cell_text in cells:
                # 自动换行处理
                wrapped = textwrap.fill(cell_text, width=col_width_chars)
                wrapped_row.append(wrapped)
                lines = wrapped.count('\n') + 1
                if lines > max_lines: max_lines = lines
            
            data.append(wrapped_row)
            row_heights.append(max_lines)

        if not data: return None

        df = pd.DataFrame(data, columns=headers)

        # 4. 绘图计算
        base_h = 0.5
        header_h = 0.6
        total_h = header_h + sum([rh * base_h for rh in row_heights]) + 0.5
        # 动态宽度：列数越多越宽，但设上限
        total_w = min(len(headers) * 3, 12) 

        fig, ax = plt.subplots(figsize=(total_w, total_h))
        ax.axis('off')
        
        # 5. 生成表格
        table = ax.table(cellText=df.values, colLabels=df.columns, loc='center', cellLoc='left')
        
        # 6. 美化样式
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        cells = table.get_celld()
        
        for (row, col), cell in cells.items():
            cell.set_edgecolor('#cccccc')
            cell.set_linewidth(0.5)
            # 设置内边距
            cell.set_text_props(position=(0.02, cell.get_text_props()['position'][1]))
            
            if row == 0:
                cell.set_height(header_h / total_h)
                cell.set_facecolor('#2c3e50')
                cell.set_text_props(color='white', weight='bold', ha='center')
            else:
                rh_mult = row_heights[row-1]
                cell.set_height((rh_mult * base_h) / total_h)
                cell.set_facecolor('#f8f9fa' if row % 2 else '#ffffff')
                cell.set_text_props(color='black', ha='left', wrap=True)

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', bbox_inches='tight', pad_inches=0.1, dpi=300)
        plt.close(fig)
        img_buffer.seek(0)
        return img_buffer

    except Exception as e:
        print(f"Table Gen Error: {e}")
        return None

def generate_professional_word(content_text, model_name):
    """
    【修复版】Word 生成逻辑：确保最后一张表也能被写入
    """
    doc = Document()
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimHei')
    
    paragraph_format = style.paragraph_format
    paragraph_format.space_after = Pt(8)
    paragraph_format.line_spacing = 1.15
    
    # 标题
    head = doc.add_heading('Investment Research Report', 0)
    head.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"Generated by AI | {datetime.now().strftime('%Y-%m-%d')}", style='Normal').alignment = WD_ALIGN_PARAGRAPH.RIGHT
    doc.add_paragraph("_" * 50)

    lines = content_text.split('\n')
    inside_table = False
    table_buffer = []

    for line in lines:
        stripped = line.strip()
        
        # 判定表格行：以 | 开头并以 | 结尾 (放宽中间内容的限制)
        is_table_row = stripped.startswith('|') and stripped.endswith('|')
        
        if is_table_row:
            inside_table = True
            table_buffer.append(stripped)
        else:
            if inside_table:
                # 表格结束，立即处理缓冲区
                img = create_professional_table_image(table_buffer)
                if img:
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    run = p.add_run()
                    run.add_picture(img, width=Inches(6.5))
                else:
                    # 如果绘图失败，回退到文本模式，防止内容丢失
                    for tb_line in table_buffer:
                        doc.add_paragraph(tb_line, style='Normal')
                
                inside_table = False
                table_buffer = []

            # 处理非表格内容
            if not stripped: continue
            
            if stripped.startswith('# '): 
                doc.add_heading(stripped.replace('#','').strip(), 1)
            elif stripped.startswith('## '): 
                doc.add_heading(stripped.replace('#','').strip(), 2)
            elif stripped.startswith('### '): 
                doc.add_heading(stripped.replace('#','').strip(), 3)
            elif stripped.startswith('- ') or stripped.startswith('* '): 
                doc.add_paragraph(stripped[2:], style='List Bullet')
            else:
                doc.add_paragraph(stripped)

    # 【关键修复】循环结束后，检查是否还遗留了一个表格在缓冲区
    if inside_table and table_buffer:
        img = create_professional_table_image(table_buffer)
        if img:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run()
            run.add_picture(img, width=Inches(6.5))
        else:
            for tb_line in table_buffer:
                doc.add_paragraph(tb_line)

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
st.title("💎 Pro Research Agent (Final Fixed)")

uploaded_file = st.file_uploader("上传 PDF", type=['pdf'])

if uploaded_file and st.button("🔥 开始完美转化"):
    api_url = "https://api.nuwaapi.com/v1/chat/completions"
    
    # 1. 逐页解析
    with st.spinner("📖 逐页读取 PDF..."):
        pages_list = extract_pages_from_pdf(uploaded_file)

    # 2. 1:1 数字化 (OCR模式)
    full_article_parts = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, page_text in enumerate(pages_list):
        status_text.markdown(f"**🔄 处理第 {i+1}/{len(pages_list)} 页 (表格重构中)...**")
        
        prompt = """
        You are an advanced OCR Engine. 
        Task: Transcribe the text exactly. 
        Rules:
        1. **Formatting**: Use Markdown (# Headers, - Lists).
        2. **Tables**: DETECT TABLES and output them as standard Markdown tables (| Header |... |---|).
        3. **Content**: No summarizing. Word-for-word exact match.
        """
        msg = [{"role": "user", "content": f"{prompt}\n\nCONTENT:\n{page_text}"}]
        
        res = call_ai_api(api_key, api_url, model_name, msg, temperature=0.1)
        
        if res:
            full_article_parts.append(res)
        else:
            full_article_parts.append(f"\n\n{page_text}\n\n") # 保底
            
        progress_bar.progress((i + 1) / len(pages_list))

    final_article = "\n\n".join(full_article_parts)
    status_text.success("✅ 内容 1:1 提取完成")

    # 3. 社媒生成 (恢复该功能)
    with st.spinner("🧠 正在撰写深度社媒 (Lead Analyst Mode)..."):
        social_prompt = """
        Act as a Lead Analyst at a Hedge Fund. 
        Write social media content based on the report provided.
        **GOAL**: Sell the Logic, Catalysts, and Upside. 
        **PLATFORMS**: 
        1. LinkedIn (Professional, bullet points)
        2. Twitter/X (Thread style, catchy)
        3. Reddit (DD style, informal depth)
        
        Split platforms with '==='.
        """
        # 截取头尾以防 token 溢出，但保留核心
        context = final_article[:8000] 
        msg_social = [{"role": "user", "content": f"{social_prompt}\n\nREPORT:\n{context}"}]
        social_res = call_ai_api(api_key, api_url, model_name, msg_social, temperature=0.7)
        
        if not social_res: social_res = "⚠️ 社媒生成超时，请重试。"

    # 4. 生成 Word
    with st.spinner("💾 正在渲染 Word (表格转图片)..."):
        word_bio = generate_professional_word(final_article, model_name)

    # 5. 存档
    report_data = {
        "time": datetime.now().strftime("%H:%M"),
        "filename": uploaded_file.name,
        "article": final_article,
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
    
    col1, col2 = st.columns([4, 6])
    
    with col1:
        st.subheader("📥 成果下载")
        st.download_button(
            "💾 下载 Word 报告 (含表格图片)",
            data=current['word_data'],
            file_name=f"Report_{current['time']}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        st.divider()
        st.subheader("📋 1:1 原始内容 (用于复制)")
        st.info("👇 这是一个纯文本区域，你可以全选复制，粘贴到任何地方。它保留了所有文字和 Markdown 符号。")
        # 【修改点】使用 text_area 而不是 code，方便普通复制
        st.text_area("Original Content", value=current['article'], height=600)

    with col2:
        st.subheader("🔥 深度社媒文案 (已恢复)")
        # 【修改点】社媒部分单独展示，高度自适应
        st.text_area("Social Media Copy", value=current['social'], height=800)

elif not uploaded_file:
    st.info("👈 请上传 PDF。本版本已强制修复表格图片生成和社媒文案逻辑。")
