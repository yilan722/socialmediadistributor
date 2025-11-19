import streamlit as st
import requests
import pdfplumber
import io
import time
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

# --- 全局配置 ---
st.set_page_config(page_title="社媒文案 Agent", layout="wide", page_icon="📱")
plt.style.use('ggplot')
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# --- 状态管理 ---
if 'history' not in st.session_state:
    st.session_state['history'] = []
if 'current_report' not in st.session_state:
    st.session_state['current_report'] = None

# --- 核心函数 ---

def extract_text_from_pdf(uploaded_file):
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text()
            if page_text:
                text += f"\n\n====== [PAGE {i+1}] ======\n{page_text}"
    return text

def split_text_into_chunks(text, chunk_size=2000):
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

def call_ai_api(api_key, base_url, model_name, messages, temperature=0.3):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model_name, "messages": messages, "temperature": temperature, "stream": False}
    try:
        # 针对 Gemini 系列，处理长文本可能需要更长响应时间，设置超时为 300秒
        response = requests.post(base_url, headers=headers, json=payload, timeout=300)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return None 
    except:
        return None

def create_table_image(markdown_table_lines):
    """Markdown表格转图片"""
    try:
        clean_rows = [line for line in markdown_table_lines if not set(line.replace('|', '').strip()) == {'-'}]
        if len(clean_rows) < 2: return None
        headers = [h.strip() for h in clean_rows[0].split('|') if h.strip()]
        data = []
        for row in clean_rows[1:]:
            row_data = [c.strip() for c in row.split('|') if c.strip() or c==""]
            if len(row_data) > len(headers): row_data = row_data[:len(headers)]
            if len(row_data) < len(headers): row_data += [""] * (len(headers) - len(row_data))
            data.append(row_data)
        if not data: return None
        
        df = pd.DataFrame(data, columns=headers)
        fig, ax = plt.subplots(figsize=(12, len(data)*0.6 + 1.5))
        ax.axis('off')
        table = ax.table(cellText=df.values, colLabels=df.columns, loc='center', cellLoc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.8)
        
        for (row, col), cell in table.get_celld().items():
            cell.set_edgecolor('#cccccc')
            if row == 0:
                cell.set_facecolor('#2c3e50')
                cell.set_text_props(color='white', weight='bold')
            else:
                cell.set_facecolor('#f8f9fa' if row % 2 else 'white')
        
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', bbox_inches='tight', dpi=300)
        plt.close(fig)
        img_buffer.seek(0)
        return img_buffer
    except:
        return None

def generate_word_doc(content_text, model_name):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Arial'
    style.font.size = Pt(10.5)
    
    doc.add_heading('Analysis Report', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"Source: Uploaded PDF | Model: {model_name}").alignment = WD_ALIGN_PARAGRAPH.RIGHT
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
                img = create_table_image(table_buffer)
                if img: 
                    doc.add_picture(img, width=Inches(6.5))
                    doc.add_paragraph("")
                inside_table = False
                table_buffer = []
            
            if stripped.startswith('# '): doc.add_heading(stripped.replace('#','').strip(), 1)
            elif stripped.startswith('## '): doc.add_heading(stripped.replace('#','').strip(), 2)
            elif stripped.startswith('### '): doc.add_heading(stripped.replace('#','').strip(), 3)
            elif stripped.startswith('- '): doc.add_paragraph(stripped[2:], style='List Bullet')
            elif stripped: doc.add_paragraph(stripped)

    if inside_table and table_buffer:
        img = create_table_image(table_buffer)
        if img: doc.add_picture(img, width=Inches(6.5))
    
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
    # 默认API Key (建议生产环境置空)
    api_key = st.text_input("API Key", value="sk-3UIO8MwTblfyQuEZz2WUCzQOuK4QwwIPALVcNxFFNUxJayu7", type="password")
    
    # === 模型列表更新 ===
    model_options = [
        "gemini-3-pro", 
        "gemini-2.5-pro", 
        "qwen-max", 
        "gpt-4o"
    ]
    model_name = st.selectbox("选择模型 (Model)", model_options)

st.title("📱 社媒文案 Agent")

uploaded_file = st.file_uploader("上传 PDF 资料", type=['pdf'])

if uploaded_file and st.button("🔥 开始生成文案 & 报告"):
    api_url = "https://api.nuwaapi.com/v1/chat/completions"
    
    # 1. 解析
    with st.spinner("📖 正在读取 PDF 内容..."):
        raw_text = extract_text_from_pdf(uploaded_file)

    # 2. 逐段转化 (带智能保底)
    chunks = split_text_into_chunks(raw_text, chunk_size=2000)
    full_article_parts = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, chunk in enumerate(chunks):
        status_text.markdown(f"**🔄 解析处理中: Part {i+1}/{len(chunks)}**")
        
        prompt = """
        You are a Document Digitizer.
        Task: Convert raw PDF text to Markdown.
        Rules:
        1. **KEEP EVERY DETAIL**. No summarizing.
        2. **Format Tables** as Markdown (|...|).
        3. **References/URLs**: Keep them exactly as is.
        """
        msg = [{"role": "user", "content": f"{prompt}\n\nCONTENT:\n{chunk}"}]
        
        # 重试逻辑
        chunk_res = None
        for attempt in range(2):
            chunk_res = call_ai_api(api_key, api_url, model_name, msg)
            if chunk_res: break
            time.sleep(1)
        
        # 智能保底
        if chunk_res:
            full_article_parts.append(chunk_res)
        else:
            fallback_text = f"\n\n> ⚠️ (Note: Section {i+1} raw content preserved due to processing complexity)\n\n{chunk}\n\n"
            full_article_parts.append(fallback_text)
            
        progress_bar.progress((i + 1) / len(chunks))

    final_article = "\n\n".join(full_article_parts)
    status_text.success("✅ 内容解析完成！")

    # 3. 社媒生成 (新闻/热点导向型)
    with st.spinner("📰 正在提炼热点并撰写社媒文案..."):
        
        # 构造上下文：头 + 尾，确保包含最新结论
        context_head = final_article[:5000]
        context_tail = final_article[-8000:] if len(final_article) > 8000 else ""
        social_context = context_head + "\n\n[...SKIPPING MIDDLE SECTIONS...]\n\n" + context_tail
        
        social_prompt = """
        You are a Viral Social Media Copywriter. Write content based on the report.
        
        **CRITICAL INSTRUCTION**: 
        - **FOCUS ON THE "NEW"**: Prioritize the most recent events, financial numbers, and future guidance (e.g., 2025 outlook).
        - **STYLE**: High energy, professional but engaging.
        
        **Platforms**:
        1. **LinkedIn**: Professional insight. Focus on "Key Takeaways" & "Strategic Direction".
        2. **Twitter (Thread)**: 5 tweets. Breaking news style. Use 🚨 emojis.
        3. **Xiaohongshu (小红书)**: "Big News!" style. Focus on money/trend. Emoji heavy.
        4. **Reddit**: Analytical discussion starter.
        
        Output in the requested languages. Split with '==='.
        """
        
        msg_social = [{"role": "user", "content": f"{social_prompt}\n\nREPORT CONTENT:\n{social_context}"}]
        social_res = call_ai_api(api_key, api_url, model_name, msg_social)
        
        if not social_res: social_res = "⚠️ 社媒生成超时，请尝试重新生成。"

    # 4. 生成 Word
    with st.spinner("💾 正在打包 Word 文档..."):
        word_bio = generate_word_doc(final_article, model_name)

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
    st.markdown(f"## 📊 当前项目: {current['filename']}")
    col1, col2 = st.columns([6, 4])
    
    with col1:
        st.download_button(
            "📥 下载详细 Word 报告",
            data=current['word_data'],
            file_name=f"Report_{current['time']}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        with st.expander("📄 原始内容预览", expanded=False):
            st.markdown(current['article'])

    with col2:
        st.success("🔥 已生成社媒文案")
        st.text_area("一键复制所有文案", value=current['social'], height=600)

elif not uploaded_file:
    st.info("👈 请上传文件。建议优先使用 'gemini-3-pro' 处理长文档。")