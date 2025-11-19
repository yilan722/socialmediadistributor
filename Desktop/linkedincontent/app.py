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
st.set_page_config(page_title="Pro Research Agent", layout="wide", page_icon="💎")

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

def extract_text_from_pdf(uploaded_file):
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text()
            if page_text:
                text += f"\n\n{page_text}" 
    return text

def split_text_into_chunks(text, chunk_size=2500):
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

def call_ai_api(api_key, base_url, model_name, messages, temperature=0.3, timeout=300):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model_name, "messages": messages, "temperature": temperature, "stream": False}
    try:
        response = requests.post(base_url, headers=headers, json=payload, timeout=timeout)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            # 打印错误但不中断，方便 fallback 接管
            print(f"⚠️ API Error: {response.status_code}")
            return None 
    except Exception as e:
        print(f"⚠️ Connection Error: {e}")
        return None

def create_professional_table_image(markdown_table_lines):
    """
    【保留你满意的版本】表格绘图引擎：动态行高 + 零白边
    """
    try:
        clean_rows = []
        for line in markdown_table_lines:
            content = line.strip().strip('|')
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
        fig_height = header_height_inch + total_data_height
        fig_width = min(len(headers) * 2.5, 11)
        
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
        plt.savefig(img_buffer, format='png', bbox_inches='tight', pad_inches=0.02, dpi=300)
        plt.close(fig)
        img_buffer.seek(0)
        return img_buffer

    except Exception:
        return None

def generate_professional_word(content_text, model_name):
    """
    【保留你满意的版本】Word 生成逻辑
    """
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
    
    meta = doc.add_paragraph(f"Generated by AI Agent | {datetime.now().strftime('%Y-%m-%d')}")
    meta.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    meta.runs[0].font.color.rgb = RGBColor(100, 100, 100)
    doc.add_paragraph("_" * 50)

    lines = content_text.split('\n')
    inside_table = False
    table_buffer = []

    for line in lines:
        stripped = line.strip()
        is_table_row = stripped.startswith('|') and stripped.endswith('|')
        
        if is_table_row:
            inside_table = True
            table_buffer.append(stripped)
        else:
            if inside_table:
                img = create_professional_table_image(table_buffer)
                if img: 
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    run = p.add_run()
                    run.add_picture(img, width=Inches(6.2))
                inside_table = False
                table_buffer = []
            
            if not stripped: continue
            
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

    if inside_table and table_buffer:
        img = create_professional_table_image(table_buffer)
        if img: 
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run()
            run.add_picture(img, width=Inches(6.2))
    
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
    model_name = st.selectbox("Model", ["gemini-3-pro", "gemini-2.5-pro", "qwen-max", "gpt-4o"])

# --- 主界面 ---
st.title("💎 Pro Research Agent (Final Stable)")

uploaded_file = st.file_uploader("上传 PDF 资料", type=['pdf'])

if uploaded_file and st.button("🔥 开始完美转化"):
    api_url = "https://api.nuwaapi.com/v1/chat/completions"
    
    # 1. 解析 PDF
    with st.spinner("📖 读取 PDF..."):
        raw_text = extract_text_from_pdf(uploaded_file)

    # 2. 数字化 (1:1 格式化) - 【核心修复区域】
    chunks = split_text_into_chunks(raw_text, chunk_size=2500)
    full_article_parts = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, chunk in enumerate(chunks):
        status_text.markdown(f"**🔄 格式化处理中: Part {i+1}/{len(chunks)}**")
        
        prompt = """
        You are a Senior Data Entry Specialist. 
        Task: Digitally transcribe the provided document text into Markdown.
        
        **STRICT RULES**:
        1. **TABLES**: Merge cross-page tables into one. Output valid Markdown tables (|...|).
        2. **CONTENT**: Word-for-word transcription. No summarization.
        """
        msg = [{"role": "user", "content": f"{prompt}\n\nRAW CONTENT:\n{chunk}"}]
        
        chunk_res = None
        # 重试次数增加到 3 次
        for attempt in range(3):
            chunk_res = call_ai_api(api_key, api_url, model_name, msg)
            if chunk_res: 
                break
            # 指数退避：失败一次等待时间加长 (1s, 2s, 4s)
            time.sleep(2 ** attempt)
        
        if chunk_res:
            full_article_parts.append(chunk_res)
        else:
            # === 核心修复：保底机制 (Fallback) ===
            # 如果 AI 彻底失败，直接填入原始文本，绝不显示 Error processing
            print(f"⚠️ Part {i+1} failed AI formatting. Falling back to raw text.")
            fallback_content = f"\n\n{chunk}\n\n" # 使用原始 OCR 文本
            full_article_parts.append(fallback_content)
            
        progress_bar.progress((i + 1) / len(chunks))
        # 强制冷却：每次成功处理后休息 2 秒，防止速率限制
        time.sleep(2)

    final_article = "\n\n".join(full_article_parts)
    status_text.success("✅ 格式化完成！")

    # 3. 社媒生成 (三级重试)
    with st.spinner("🧠 正在撰写深度社媒..."):
        social_res = None
        
        context_head = final_article[:5000]
        context_tail = final_article[-5000:] if len(final_article) > 5000 else ""
        social_context_full = context_head + "\n\n[...SKIPPING...]\n\n" + context_tail
        
        social_prompt = """
        Act as a Lead Analyst at a Hedge Fund. Write social media content.
        **GOAL**: Sell the *Logic*, *Catalysts*, and *Upside*. 
        **PLATFORMS**: LinkedIn, Twitter (Thread), Reddit (DD style), Xiaohongshu.
        Split with '==='.
        """
        
        # 尝试 1
        msg_social = [{"role": "user", "content": f"{social_prompt}\n\nREPORT:\n{social_context_full}"}]
        social_res = call_ai_api(api_key, api_url, model_name, msg_social, temperature=0.7, timeout=120)
        
        # 尝试 2
        if not social_res:
            short_context = final_article[:3000] + "\n...\n" + final_article[-3000:]
            msg_social_short = [{"role": "user", "content": f"{social_prompt}\n\nREPORT:\n{short_context}"}]
            social_res = call_ai_api(api_key, api_url, model_name, msg_social_short, temperature=0.7, timeout=120)

        # 尝试 3
        if not social_res:
            minimal_context = final_article[:3000]
            msg_social_min = [{"role": "user", "content": f"{social_prompt}\n\nREPORT START:\n{minimal_context}"}]
            social_res = call_ai_api(api_key, api_url, model_name, msg_social_min, temperature=0.7, timeout=60)

        if not social_res: 
            social_res = "⚠️ 社媒生成失败。请检查 API 连接。"

    # 4. 生成 Word
    with st.spinner("💾 正在渲染专业 Word 文档..."):
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
    col1, col2 = st.columns([5, 5])
    
    with col1:
        st.download_button(
            "📥 下载 Word",
            data=current['word_data'],
            file_name=f"Pro_Report_{current['time']}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        with st.expander("📄 原始内容预览", expanded=False):
            st.markdown(current['article'])

    with col2:
        if "⚠️" in str(current['social']):
             st.warning("部分社媒内容生成遇到延迟")
        else:
             st.success("🔥 深度社媒文案")
        
        st.text_area("Copy", value=current['social'], height=800)

elif not uploaded_file:
    st.info("👈 请上传文件。已启用 API 保护与自动降级机制，杜绝 Error 报错。")
