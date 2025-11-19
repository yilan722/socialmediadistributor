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

# 配置绘图风格 (支持中文和特殊符号)
plt.style.use('ggplot')
plt.rcParams['font.family'] = 'sans-serif'
# 尝试多种字体以适配不同服务器环境
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial', 'DejaVu Sans', 'Microsoft YaHei'] 
plt.rcParams['axes.unicode_minus'] = False

# --- 状态管理 ---
if 'history' not in st.session_state:
    st.session_state['history'] = []
if 'current_report' not in st.session_state:
    st.session_state['current_report'] = None

# --- 核心功能函数 ---

def extract_text_from_pdf(uploaded_file):
    """
    提取PDF文本。不按页强行分割，而是提供流式文本，
    有助于模型理解跨页表格。
    """
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text()
            if page_text:
                text += f"\n\n{page_text}" 
    return text

def split_text_into_chunks(text, chunk_size=2500):
    """切分长文本"""
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

def call_ai_api(api_key, base_url, model_name, messages, temperature=0.3, timeout=300):
    """
    增强版 API 调用：支持自定义超时，返回详细错误
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model_name, "messages": messages, "temperature": temperature, "stream": False}
    try:
        response = requests.post(base_url, headers=headers, json=payload, timeout=timeout)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            print(f"⚠️ API Error: {response.status_code} - {response.text[:100]}")
            return None 
    except Exception as e:
        print(f"⚠️ Connection Error: {e}")
        return None

def create_professional_table_image(markdown_table_lines):
    """
    【终极版】表格绘图引擎：
    1. 动态行高计算：根据文字量自动撑开单元格，杜绝重叠。
    2. 零白边：图片紧贴表格边缘。
    3. 强力清洗：过滤 Markdown 分隔符。
    """
    try:
        # --- 1. 数据清洗与解析 ---
        clean_rows = []
        for line in markdown_table_lines:
            content = line.strip().strip('|')
            # 过滤掉只包含分隔符(-, :, |)的行
            if not content or set(content.replace('|', '').strip()) <= {'-', ':', ' '}:
                continue
            clean_rows.append(line)

        if len(clean_rows) < 2: return None
        
        # 提取表头
        headers = [h.strip() for h in clean_rows[0].split('|') if h.strip()]
        if not headers: return None
        
        # 提取数据并预处理
        data = []
        row_heights = [] # 记录每一行需要的倍数高度
        col_width_chars = 25 # 设定每列大约多少字符换行
        
        for row_line in clean_rows[1:]:
            raw_cells = [c.strip() for c in row_line.split('|') if c.strip() or c==""]
            
            # 对齐列数
            if len(raw_cells) > len(headers): raw_cells = raw_cells[:len(headers)]
            if len(raw_cells) < len(headers): raw_cells += [""] * (len(headers) - len(raw_cells))
            
            wrapped_row = []
            max_lines_in_row = 1
            
            for cell_text in raw_cells:
                # 强制换行处理
                wrapped_text = textwrap.fill(cell_text, width=col_width_chars, break_long_words=True)
                wrapped_row.append(wrapped_text)
                
                # 计算该单元格占用的行数
                lines_count = wrapped_text.count('\n') + 1
                if lines_count > max_lines_in_row:
                    max_lines_in_row = lines_count
            
            data.append(wrapped_row)
            row_heights.append(max_lines_in_row)

        if not data: return None
        
        df = pd.DataFrame(data, columns=headers)

        # --- 2. 动态计算图片尺寸 ---
        base_row_height_inch = 0.45 # 基础行高
        header_height_inch = 0.6    # 表头高度
        
        # 总高度 = 表头 + 所有数据行的高度和
        total_data_height = sum([rh * base_row_height_inch for rh in row_heights])
        fig_height = header_height_inch + total_data_height
        
        # 总宽度
        fig_width = min(len(headers) * 2.5, 11) # 限制最大宽度
        
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        ax.axis('off')
        
        # --- 3. 绘制表格 ---
        table = ax.table(cellText=df.values, colLabels=df.columns, loc='center', cellLoc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        
        # --- 4. 样式精修 ---
        cells = table.get_celld()
        
        for (row, col), cell in cells.items():
            cell.set_edgecolor('#d0d0d0')
            cell.set_linewidth(0.5)
            
            if row == 0:
                # 表头样式
                cell.set_height(header_height_inch / fig_height)
                cell.set_facecolor('#2c3e50')
                cell.set_text_props(color='white', weight='bold')
            else:
                # 数据行样式
                height_multiplier = row_heights[row-1]
                # 设置该行高度比例
                cell.set_height((height_multiplier * base_row_height_inch) / fig_height)
                
                cell.set_facecolor('#f9f9f9' if row % 2 else '#ffffff')
                cell.set_text_props(color='#333333')
                # 左对齐并增加内边距
                cell.set_text_props(ha='left')
                cell.set_text_props(position=(0.02, cell.get_text_props()['position'][1]))

        # --- 5. 保存图片 (去白边) ---
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', bbox_inches='tight', pad_inches=0.02, dpi=300)
        plt.close(fig)
        img_buffer.seek(0)
        return img_buffer

    except Exception as e:
        print(f"Table Render Failed: {e}")
        return None

def generate_professional_word(content_text, model_name):
    """
    生成 MBB 咨询级 Word 文档
    """
    doc = Document()
    
    # 全局样式设置
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)
    # 设置中文字体
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimHei')
    
    # 段落格式
    paragraph_format = style.paragraph_format
    paragraph_format.space_after = Pt(8)
    paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    paragraph_format.line_spacing = 1.15
    paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    # 抬头
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
            # 表格渲染逻辑
            if inside_table:
                img = create_professional_table_image(table_buffer)
                if img: 
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    run = p.add_run()
                    run.add_picture(img, width=Inches(6.2)) # 适应A4页面宽度
                inside_table = False
                table_buffer = []
            
            if not stripped: continue
            
            # 标题与正文渲染
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

    # 处理文末残留表格
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
    else:
        st.caption("暂无记录")
    
    st.divider()
    api_key = st.text_input("API Key", value="sk-3UIO8MwTblfyQuEZz2WUCzQOuK4QwwIPALVcNxFFNUxJayu7", type="password")
    model_name = st.selectbox("Model", ["gemini-3-pro", "gemini-2.5-pro", "qwen-max", "gpt-4o"])

# --- 主界面 ---
st.title("💎 Pro Research Agent (Final Ver.)")
st.caption("MBB-Style Reports | Visualized Tables | Deep Reddit DD")

uploaded_file = st.file_uploader("上传 PDF 资料", type=['pdf'])

if uploaded_file and st.button("🔥 开始完美转化"):
    api_url = "https://api.nuwaapi.com/v1/chat/completions"
    
    # 1. 解析 PDF
    with st.spinner("📖 读取 PDF..."):
        raw_text = extract_text_from_pdf(uploaded_file)

    # 2. 数字化 (1:1 格式化)
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
        3. **FORMAT**: Keep headers and lists structure.
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

    # 3. 社媒生成 (带重试机制)
    with st.spinner("🧠 正在撰写深度社媒 (Retrying enabled)..."):
        
        social_res = None
        
        # 上下文策略 1: 完整上下文
        context_head = final_article[:5000]
        context_tail = final_article[-5000:] if len(final_article) > 5000 else ""
        social_context_full = context_head + "\n\n[...SKIPPING...]\n\n" + context_tail
        
        social_prompt = """
        Act as a Lead Analyst at a Hedge Fund. Write social media content.
        
        **CORE GOAL**: Sell the *Logic*, *Catalysts*, and *Upside*. 
        **DO NOT** write a summary. Write an **INVESTMENT THESIS**.
        
        **PLATFORMS**:
        
        ### 🔵 LinkedIn
        - Professional analysis of the Moat/Strategy.
        
        ### ⚫ Twitter (Thread)
        - Hook with a shocking number.
        - 5 Tweets on "Asymmetric Upside".
        
        ### 🔴 Reddit (r/SecurityAnalysis Style DD)
        - **Title**: [DD] [Ticker] - The Bull/Bear Case (Deep Dive)
        - **Structure**: TL;DR -> The Thesis -> The Numbers -> The Risks -> Conclusion.
        - **Tone**: Objective, analytical, hard-core.
        
        ### 🟠 Xiaohongshu
        - Title: ⚠️认知差！真正的爆发逻辑
        - Focus on: Catalyst & Next Big Thing.
        
        Split with '==='.
        """
        
        # 尝试 1
        msg_social = [{"role": "user", "content": f"{social_prompt}\n\nREPORT:\n{social_context_full}"}]
        social_res = call_ai_api(api_key, api_url, model_name, msg_social, temperature=0.7, timeout=120)
        
        # 尝试 2 (缩减上下文)
        if not social_res:
            print("Retry 1: Reducing context size...")
            short_context = final_article[:3000] + "\n...\n" + final_article[-3000:]
            msg_social_short = [{"role": "user", "content": f"{social_prompt}\n\nREPORT:\n{short_context}"}]
            social_res = call_ai_api(api_key, api_url, model_name, msg_social_short, temperature=0.7, timeout=120)

        # 尝试 3 (极简)
        if not social_res:
            print("Retry 2: Minimal context...")
            minimal_context = final_article[:3000]
            msg_social_min = [{"role": "user", "content": f"{social_prompt}\n\nREPORT START:\n{minimal_context}"}]
            social_res = call_ai_api(api_key, api_url, model_name, msg_social_min, temperature=0.7, timeout=60)

        if not social_res: 
            social_res = "⚠️ 社媒生成失败。请检查 API 连接或稍后重试。"

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
            "📥 下载 Word (咨询级排版+高清图表)",
            data=current['word_data'],
            file_name=f"Pro_Report_{current['time']}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        with st.expander("📄 原始内容预览", expanded=False):
            st.markdown(current['article'])

    with col2:
        if "⚠️" in current['social']:
             st.error("社媒生成部分失败")
        else:
             st.success("🔥 深度社媒文案 (Reddit DD & Insight)")
        
        st.text_area("Copy", value=current['social'], height=800)

elif not uploaded_file:
    st.info("👈 请上传文件。系统将执行完美复刻与深度分析。")
