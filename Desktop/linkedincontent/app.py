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
st.set_page_config(page_title="Pro Research Agent (1:1 Exact Copy)", layout="wide", page_icon="💎")

# 配置绘图风格
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
    """
    按页提取文本，而不是合并成一大坨。
    这是保证表格不被打断、内容不丢失的关键。
    """
    pages_content = []
    with pdfplumber.open(uploaded_file) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                # 标记页码，帮助 AI 理解上下文，但要求 AI 输出时去掉
                pages_content.append(text)
    return pages_content

def call_ai_api(api_key, base_url, model_name, messages, temperature=0.1, timeout=300):
    """
    温度设为 0.1，尽可能降低 AI 的创造性，强制它做“复读机”以保证内容精确。
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model_name, "messages": messages, "temperature": temperature, "stream": False}
    try:
        response = requests.post(base_url, headers=headers, json=payload, timeout=timeout)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            print(f"⚠️ API Error: {response.status_code} - {response.text}")
            return None 
    except Exception as e:
        print(f"⚠️ Connection Error: {e}")
        return None

def create_professional_table_image(markdown_table_lines):
    """
    表格绘图引擎：保持原有逻辑，生成高质量表格图片
    """
    try:
        clean_rows = []
        for line in markdown_table_lines:
            content = line.strip().strip('|')
            # 过滤掉分割线行 (e.g. |---|---|)
            if not content or set(content.replace('|', '').strip()) <= {'-', ':', ' '}:
                continue
            clean_rows.append(line)

        if len(clean_rows) < 2: return None
        
        headers = [h.strip() for h in clean_rows[0].split('|') if h.strip()]
        if not headers: return None
        
        data = []
        row_heights = []
        col_width_chars = 25
        
        for row_line in clean_rows[1:]:
            raw_cells = [c.strip() for c in row_line.split('|') if c.strip() or c==""]
            # 对齐列数
            if len(raw_cells) > len(headers): raw_cells = raw_cells[:len(headers)]
            if len(raw_cells) < len(headers): raw_cells += [""] * (len(headers) - len(raw_cells))
            
            wrapped_row = []
            max_lines_in_row = 1
            
            for cell_text in raw_cells:
                wrapped_text = textwrap.fill(cell_text, width=col_width_chars, break_long_words=True)
                wrapped_row.append(wrapped_text)
                lines_count = wrapped_text.count('\n') + 1
                if lines_count > max_lines_in_row:
                    max_lines_in_row = lines_count
            
            data.append(wrapped_row)
            row_heights.append(max_lines_in_row)

        if not data: return None
        
        df = pd.DataFrame(data, columns=headers)

        base_row_height_inch = 0.45
        header_height_inch = 0.6
        total_data_height = sum([rh * base_row_height_inch for rh in row_heights])
        fig_height = header_height_inch + total_data_height + 0.5 # 增加一点底部padding
        fig_width = min(len(headers) * 2.8, 12) #稍微加宽
        
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        ax.axis('off')
        
        table = ax.table(cellText=df.values, colLabels=df.columns, loc='center', cellLoc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        
        cells = table.get_celld()
        for (row, col), cell in cells.items():
            cell.set_edgecolor('#d0d0d0')
            cell.set_linewidth(0.5)
            if row == 0:
                cell.set_height(header_height_inch / fig_height)
                cell.set_facecolor('#2c3e50')
                cell.set_text_props(color='white', weight='bold')
            else:
                height_multiplier = row_heights[row-1]
                cell.set_height((height_multiplier * base_row_height_inch) / fig_height)
                cell.set_facecolor('#f9f9f9' if row % 2 else '#ffffff')
                cell.set_text_props(color='#333333', ha='left')
                cell.set_text_props(position=(0.02, cell.get_text_props()['position'][1]))

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', bbox_inches='tight', pad_inches=0.05, dpi=300)
        plt.close(fig)
        img_buffer.seek(0)
        return img_buffer

    except Exception as e:
        print(f"Table generation failed: {e}")
        return None

def generate_professional_word(content_text, model_name):
    doc = Document()
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimHei')
    
    paragraph_format = style.paragraph_format
    paragraph_format.space_after = Pt(8)
    paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    paragraph_format.line_spacing = 1.15
    paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    head = doc.add_heading('Investment Research Report', 0)
    head.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    meta = doc.add_paragraph(f"Original Content Transcribed by AI | {datetime.now().strftime('%Y-%m-%d')}")
    meta.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    meta.runs[0].font.color.rgb = RGBColor(100, 100, 100)
    doc.add_paragraph("_" * 50)

    lines = content_text.split('\n')
    inside_table = False
    table_buffer = []

    for line in lines:
        stripped = line.strip()
        # 判定表格行的逻辑优化：首尾有|，且中间也有|
        is_table_row = stripped.startswith('|') and stripped.endswith('|') and '|' in stripped[1:-1]
        
        if is_table_row:
            inside_table = True
            table_buffer.append(stripped)
        else:
            if inside_table:
                # 表格结束，开始绘制
                img = create_professional_table_image(table_buffer)
                if img: 
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    run = p.add_run()
                    run.add_picture(img, width=Inches(6.5)) # 加宽图片
                # 即使画图失败，也把原始Markdown表格文本写入，防止数据丢失
                else:
                    for tb_line in table_buffer:
                        doc.add_paragraph(tb_line, style='Normal')
                
                inside_table = False
                table_buffer = []
            
            if not stripped: continue
            
            # 标题处理
            if stripped.startswith('# '): 
                h = doc.add_heading(stripped.replace('#','').strip(), 1)
                h.paragraph_format.space_before = Pt(18)
            elif stripped.startswith('## '): 
                h = doc.add_heading(stripped.replace('#','').strip(), 2)
                h.paragraph_format.space_before = Pt(12)
            elif stripped.startswith('### '): 
                h = doc.add_heading(stripped.replace('#','').strip(), 3)
            elif stripped.startswith('- ') or stripped.startswith('* '): 
                doc.add_paragraph(stripped[2:], style='List Bullet')
            else:
                doc.add_paragraph(stripped)

    # 处理文档末尾可能的表格
    if inside_table and table_buffer:
        img = create_professional_table_image(table_buffer)
        if img: 
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run()
            run.add_picture(img, width=Inches(6.5))
        else:
             for tb_line in table_buffer:
                doc.add_paragraph(tb_line, style='Normal')
    
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
    # 默认 key 和 model，建议使用上下文窗口大的模型
    api_key = st.text_input("API Key", value="sk-3UIO8MwTblfyQuEZz2WUCzQOuK4QwwIPALVcNxFFNUxJayu7", type="password")
    # 强力推荐使用 gemini-1.5-pro 或 gpt-4o 来处理复杂格式
    model_name = st.selectbox("Model", ["gemini-3-pro", "gpt-4o", "qwen-max", "gemini-2.5-pro"])

# --- 主界面 ---
st.title("💎 Pro Research Agent (1:1 Perfect Copy)")
st.markdown("**Mode: Exact Transcription (Table Preservation)**")

uploaded_file = st.file_uploader("上传 PDF 资料 (建议使用原版PDF，非扫描件)", type=['pdf'])

if uploaded_file and st.button("🔥 开始完美转化"):
    api_url = "https://api.nuwaapi.com/v1/chat/completions"
    
    # 1. 解析 PDF (按页)
    with st.spinner("📖 逐页读取 PDF..."):
        pages_list = extract_pages_from_pdf(uploaded_file)
        st.toast(f"共识别到 {len(pages_list)} 页，开始逐页数字化...")

    # 2. 数字化 (Page-by-Page Processing)
    full_article_parts = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, page_text in enumerate(pages_list):
        status_text.markdown(f"**🔄 正在处理第 {i+1}/{len(pages_list)} 页 (保留表格结构)...**")
        
        # --- 核心 Prompt 修改：强制 OCR 模式 ---
        prompt = """
        You are an advanced OCR and Formatting Engine. 
        Your Goal: Convert the provided text into PERFECT Markdown.
        
        STRICT EXECUTION RULES:
        1. **NO SUMMARIZATION**: You must output the text word-for-word. Do not delete any paragraphs.
        2. **TABLES ARE SACRED**: 
           - You MUST detect every table, even if it looks like a list.
           - You MUST output them as valid Markdown Tables (using | header | ... and |---| separator).
           - Do not skip numerical data.
        3. **FORMATTING**: Use # for headers, ## for subheaders, - for lists.
        4. **CLEANUP**: Remove page numbers like "Page 1 of 10" or footer dates.
        
        Input Text:
        """
        
        msg = [{"role": "user", "content": f"{prompt}\n\n{page_text}"}]
        
        page_res = None
        for attempt in range(3):
            # Temperature = 0.1 确保精确复制
            page_res = call_ai_api(api_key, api_url, model_name, msg, temperature=0.1)
            if page_res: 
                break
            time.sleep(2)
        
        if page_res:
            full_article_parts.append(page_res)
        else:
            print(f"⚠️ Page {i+1} failed. Falling back to raw text.")
            # 如果 AI 失败，用代码块包裹原始文本，提示用户手动处理
            fallback_content = f"\n\n> **[Page {i+1} Raw Text]**\n```\n{page_text}\n```\n\n" 
            full_article_parts.append(fallback_content)
            
        progress_bar.progress((i + 1) / len(pages_list))

    final_article = "\n\n".join(full_article_parts)
    status_text.success("✅ 1:1 数字化完成！表格已重建。")

    # 3. 生成 Word
    with st.spinner("💾 正在渲染专业 Word (含图表)..."):
        word_bio = generate_professional_word(final_article, model_name)

    # 4. 存档
    report_data = {
        "time": datetime.now().strftime("%H:%M"),
        "filename": uploaded_file.name,
        "article": final_article,
        "word_data": word_bio.getvalue()
    }
    st.session_state['current_report'] = report_data
    st.session_state['history'].append(report_data)
    st.rerun()

# --- 结果展示 ---
current = st.session_state['current_report']

if current:
    st.divider()
    st.markdown(f"## 📊 交付结果: {current['filename']}")
    
    tab1, tab2 = st.tabs(["📥 Word 下载 & 预览", "📝 纯 Markdown (用于复制)"])
    
    with tab1:
        col1, col2 = st.columns([3, 7])
        with col1:
            st.info("👇 点击下载包含完美表格的 Word 文档")
            st.download_button(
                "📥 下载专业 Word 报告",
                data=current['word_data'],
                file_name=f"Pro_Report_{current['time']}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
        with col2:
            st.markdown("### 📄 渲染效果预览")
            # 这里使用 st.markdown 渲染，可以看到表格效果
            st.markdown(current['article'])

    with tab2:
        st.warning("提示：点击右上角复制按钮，即可获得带格式的纯文本（含 Markdown 表格源码）")
        st.code(current['article'], language="markdown")

elif not uploaded_file:
    st.info("👈 请上传 PDF 文件。本模式将开启‘OCR级’逐页精细处理，确保表格和全文内容 100% 完整。")
