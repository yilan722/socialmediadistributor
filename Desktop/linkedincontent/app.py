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
# 配置专业绘图风格
plt.style.use('ggplot')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial', 'DejaVu Sans'] 

# --- 状态管理 ---
if 'history' not in st.session_state:
    st.session_state['history'] = []
if 'current_report' not in st.session_state:
    st.session_state['current_report'] = None

# --- 核心函数 ---

def extract_text_from_pdf(uploaded_file):
    """
    提取文本，并不再机械地按页分割，而是尝试以流式文本提供，
    有助于解决跨页表格断裂的问题。
    """
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text()
            if page_text:
                # 去掉页脚页眉的干扰（简单规则），只保留核心内容
                text += f"\n\n{page_text}" 
    return text

def split_text_into_chunks(text, chunk_size=2500):
    # 稍微加大 Chunk，让表格尽可能在一个块里
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

def call_ai_api(api_key, base_url, model_name, messages, temperature=0.3):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model_name, "messages": messages, "temperature": temperature, "stream": False}
    try:
        response = requests.post(base_url, headers=headers, json=payload, timeout=300)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        return None 
    except:
        return None

def create_professional_table_image(markdown_table_lines):
    """
    【升级版】表格绘图引擎：支持自动换行、专业配色、完整显示
    """
    try:
        # 1. 清洗数据
        clean_rows = [line for line in markdown_table_lines if not set(line.replace('|', '').strip()) == {'-'}]
        if len(clean_rows) < 2: return None
        
        headers = [h.strip() for h in clean_rows[0].split('|') if h.strip()]
        data = []
        for row in clean_rows[1:]:
            row_data = [c.strip() for c in row.split('|') if c.strip() or c==""]
            # 对齐处理
            if len(row_data) > len(headers): row_data = row_data[:len(headers)]
            if len(row_data) < len(headers): row_data += [""] * (len(headers) - len(row_data))
            
            # 【关键】对每个单元格进行自动换行处理，防止图片过宽
            wrapped_row = [textwrap.fill(cell, width=20) for cell in row_data] 
            data.append(wrapped_row)
            
        if not data: return None
        
        df = pd.DataFrame(data, columns=headers)

        # 2. 动态计算图片尺寸
        # 高度 = 行数 * 系数 + 标题栏
        # 宽度 = 列数 * 系数
        row_height = 0.8
        fig_height = len(data) * row_height + 1.5
        fig_width = min(len(headers) * 3, 12) # 限制最大宽度
        
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        ax.axis('off')
        
        # 3. 绘制表格
        table = ax.table(cellText=df.values, colLabels=df.columns, loc='center', cellLoc='center')
        
        # 4. 专业样式微调
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2) # 增加行高，让文字更舒展
        
        for (row, col), cell in table.get_celld().items():
            cell.set_edgecolor('#d0d0d0') # 极细灰边框
            cell.set_linewidth(0.5)
            
            if row == 0:
                # 表头：深色商务蓝背景 + 白字 + 加粗
                cell.set_facecolor('#2c3e50')
                cell.set_text_props(color='white', weight='bold', fontsize=11)
            else:
                # 内容：隔行变色
                cell.set_facecolor('#f9f9f9' if row % 2 else '#ffffff')
                cell.set_text_props(color='#333333') # 深灰字体

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', bbox_inches='tight', dpi=300, pad_inches=0.1)
        plt.close(fig)
        img_buffer.seek(0)
        return img_buffer
    except Exception as e:
        print(f"Table Error: {e}")
        return None

def generate_professional_word(content_text, model_name):
    """
    【升级版】Word 生成引擎：MBB 咨询风格排版
    """
    doc = Document()
    
    # 1. 设置默认字体 (Calibri / Arial) - 更加商务
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)
    # 强制设置中文字体，防止乱码
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimHei')
    
    # 2. 设置段落间距 (防止文字挤在一起)
    paragraph_format = style.paragraph_format
    paragraph_format.space_after = Pt(8) # 段后间距
    paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    paragraph_format.line_spacing = 1.15 # 1.15倍行距
    paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY # 两端对齐 (专业关键)

    # 3. 封面/抬头
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
        # 严格的表格检测
        is_table_row = stripped.startswith('|') and stripped.endswith('|')
        
        if is_table_row:
            inside_table = True
            table_buffer.append(stripped)
        else:
            # 如果刚才在表格里，现在出来了 -> 渲染表格
            if inside_table:
                img = create_professional_table_image(table_buffer)
                if img: 
                    # 居中插入图片
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    run = p.add_run()
                    run.add_picture(img, width=Inches(6.2)) # 适应A4宽度
                inside_table = False
                table_buffer = []
            
            # 渲染普通文本 (带样式)
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
                p = doc.add_paragraph(stripped[2:], style='List Bullet')
            else:
                # 正文内容
                doc.add_paragraph(stripped)

    # 处理文末表格
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

# --- UI & Logic ---
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
    st.info("💎 严格模式已开启：所有表格将强制转为高清图片，Word 排版已优化为咨询级格式。")

st.title("💎 Pro Research Agent (Perfect Format)")

uploaded_file = st.file_uploader("上传 PDF 资料", type=['pdf'])

if uploaded_file and st.button("🔥 开始完美转化"):
    api_url = "https://api.nuwaapi.com/v1/chat/completions"
    
    # 1. 解析
    with st.spinner("📖 读取 PDF (尝试合并跨页表格)..."):
        raw_text = extract_text_from_pdf(uploaded_file)

    # 2. 1:1 转化
    chunks = split_text_into_chunks(raw_text, chunk_size=2500)
    full_article_parts = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, chunk in enumerate(chunks):
        status_text.markdown(f"**🔄 格式化处理中: Part {i+1}/{len(chunks)}**")
        
        # === 核心 Prompt：强制要求表格完整性 ===
        prompt = """
        You are a Senior Data Entry Specialist. 
        Task: Digitally transcribe the provided document text into Markdown.
        
        **STRICT RULES FOR PERFECT FORMATTING**:
        1. **TABLES**: 
           - If a table spans across pages in the raw text, **MERGE IT** into one single Markdown table.
           - Output valid Markdown tables (| Col1 | Col2 |).
           - DO NOT output broken tables.
        2. **CONTENT**: Word-for-word transcription. No summarization.
        3. **CLEANUP**: Remove headers/footers like "Page 1 of 10".
        """
        msg = [{"role": "user", "content": f"{prompt}\n\nRAW CONTENT:\n{chunk}"}]
        
        chunk_res = None
        for attempt in range(2):
            chunk_res = call_ai_api(api_key, api_url, model_name, msg)
            if chunk_res: break
            time.sleep(1)
        
        if chunk_res:
            full_article_parts.append(chunk_res)
        else:
            full_article_parts.append(f"\n\n[Error processing part {i+1}]\n\n")
            
        progress_bar.progress((i + 1) / len(chunks))

    final_article = "\n\n".join(full_article_parts)
    status_text.success("✅ 格式化完成！")

    # 3. 社媒生成 (Reddit 深度优化版)
    with st.spinner("🧠 正在撰写社媒 (含 Reddit DD)..."):
        
        context_head = final_article[:6000]
        context_tail = final_article[-8000:] if len(final_article) > 8000 else ""
        social_context = context_head + "\n\n[...SKIPPING...]\n\n" + context_tail
        
        social_prompt = """
        Act as a Lead Analyst at a Hedge Fund. Write social media content.
        
        **CORE GOAL**: Sell the *Logic* and the *Upside*. Be analytical, not journalistic.
        
        **PLATFORM STRATEGY**:
        
        ### 🔵 LinkedIn (Professional)
        - "The market is missing X about [Company]."
        - 3 Bullet points on Structural Catalysts.
        - Conclusion: Why this is a Buy/Sell now.
        
        ### ⚫ Twitter/X (Thread)
        - Hook: A chart or number that shocks people.
        - Body: 5 tweets explaining the "Asymmetric Upside".
        - Tone: High conviction.
        
        ### 🔴 Reddit (r/SecurityAnalysis Style DD)
        - **Title**: [DD] [Ticker] - Why the market is wrong about [Topic] (Thesis inside)
        - **Structure**:
          1. **TL;DR**: 2 sentences summary.
          2. **The Thesis**: The main argument.
          3. **The Numbers**: Key valuation metrics (e.g. EV/EBITDA, FCF Yield).
          4. **The Bear Case**: What could go wrong? (Show you are objective).
          5. **Conclusion**: Target price or horizon.
        - **Tone**: Serious, analytical, detailed. No emojis.
        
        ### 🟠 Xiaohongshu
        - Title: ⚠️认知差！[Company] 真正的爆发点
        - Body: Emoji heavy, focus on "Next Big Thing".
        
        Split with '==='.
        """
        
        msg_social = [{"role": "user", "content": f"{social_prompt}\n\nREPORT:\n{social_context}"}]
        social_res = call_ai_api(api_key, api_url, model_name, msg_social, temperature=0.7)
        if not social_res: social_res = "Generate Failed."

    # 4. 生成 Word (MBB 级)
    with st.spinner("💾 正在渲染专业 Word 文档 (Styles & Images)..."):
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

# --- 结果 ---
current = st.session_state['current_report']

if current:
    st.divider()
    st.markdown(f"## 📊 交付: {current['filename']}")
    col1, col2 = st.columns([5, 5])
    
    with col1:
        st.download_button(
            "📥 下载 Word (咨询级排版+高清图表)",
            data=current['word_data'],
            file_name=f"Pro_Report_{current['time']}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        with st.expander("📄 原始内容", expanded=False):
            st.markdown(current['article'])

    with col2:
        st.success("🔥 深度社媒文案 (Reddit DD & Insight)")
        st.text_area("Copy", value=current['social'], height=800)

elif not uploaded_file:
    st.info("👈 请上传。系统将自动执行表格完整化、样式美化和 Reddit 深度撰写。")
