import streamlit as st
import streamlit.components.v1 as components
import requests
import pdfplumber
import io
import textwrap
import pandas as pd
import matplotlib.pyplot as plt
import base64
from datetime import datetime
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

# --- 全局配置 ---
st.set_page_config(page_title="Pro Research (Copy Button Fixed)", layout="wide", page_icon="💎")

# 绘图配置 (解决中文乱码)
plt.style.use('ggplot')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial', 'Microsoft YaHei', 'DejaVu Sans'] 
plt.rcParams['axes.unicode_minus'] = False

# --- 状态管理 ---
if 'history' not in st.session_state:
    st.session_state['history'] = []
if 'current_report' not in st.session_state:
    st.session_state['current_report'] = None

# --- 核心函数 ---

def extract_text(uploaded_file):
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t: text += f"\n{t}"
    return text

def call_ai(api_key, model, messages):
    url = "https://api.nuwaapi.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": 0.1, "stream": False}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=120)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content']
        return None
    except: return None

def fig_to_base64(fig):
    """把 matplotlib 图片转为 base64 字符串"""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=150, pad_inches=0.1)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode()

def create_table_img_b64(markdown_lines):
    """
    强制把 list 转换为图片 Base64
    """
    try:
        # 1. 清洗
        clean_rows = [line.strip() for line in markdown_lines if '|' in line and not set(line.strip()) <= {'|', '-', ':', ' '}]
        if len(clean_rows) < 1: return None
        
        # 2. 解析
        data = []
        max_cols = 0
        for line in clean_rows:
            cells = [c.strip() for c in line.strip('|').split('|')]
            data.append(cells)
            max_cols = max(max_cols, len(cells))
            
        if not data: return None
        
        # 补齐
        final_data = [row + [""]*(max_cols-len(row)) for row in data]
        
        headers = final_data[0]
        body = final_data[1:]
        if not body: body = [[""]*len(headers)]
        
        # 3. 绘图
        df = pd.DataFrame(body, columns=headers)
        
        # 动态高度
        row_heights = []
        col_width = 25
        for row in body:
            mh = 1
            for c in row:
                mh = max(mh, len(textwrap.wrap(str(c), width=col_width)))
            row_heights.append(mh)
            
        total_h = 0.8 + sum([h*0.45 for h in row_heights])
        total_w = min(len(headers)*3, 12)
        
        fig, ax = plt.subplots(figsize=(total_w, total_h))
        ax.axis('off')
        
        table = ax.table(cellText=df.values, colLabels=df.columns, loc='center', cellLoc='left')
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        
        # 样式
        cells = table.get_celld()
        for (row, col), cell in cells.items():
            cell.set_edgecolor('#cccccc')
            cell.set_linewidth(1)
            cell.set_text_props(position=(0.02, cell.get_text_props()['position'][1]))
            if row == 0:
                cell.set_facecolor('#2c3e50')
                cell.set_text_props(color='white', weight='bold', ha='center')
            else:
                cell.set_facecolor('#f9f9f9' if row%2 else 'white')
                cell.set_text_props(color='black', wrap=True)
                
        return fig_to_base64(fig)
    except Exception as e:
        print(f"Table Error: {e}")
        return None

def process_content_to_html(text):
    """
    将文本转为 HTML，表格强制转为 Base64 图片
    """
    lines = text.split('\n')
    html_out = """<div id="content-to-copy" style="font-family: Arial; padding: 20px; color: #333;">"""
    
    table_buffer = []
    inside_table = False
    
    for line in lines:
        stripped = line.strip()
        # 只要包含 | 就认为是表格的一部分
        is_table_row = '|' in stripped
        
        if is_table_row:
            inside_table = True
            table_buffer.append(stripped)
        else:
            if inside_table:
                # 结束表格，生成图片
                b64 = create_table_img_b64(table_buffer)
                if b64:
                    html_out += f'<br><img src="data:image/png;base64,{b64}" style="max-width:100%; border:1px solid #ddd;" /><br>'
                else:
                    # 如果生成图片失败，回退到文本
                    for tb in table_buffer:
                         html_out += f"<p>{tb}</p>"
                inside_table = False
                table_buffer = []
            
            # 处理普通文本
            if stripped.startswith('# '): html_out += f"<h1>{stripped[2:]}</h1>"
            elif stripped.startswith('## '): html_out += f"<h2>{stripped[3:]}</h2>"
            elif stripped.startswith('### '): html_out += f"<h3>{stripped[4:]}</h3>"
            elif stripped.startswith('- '): html_out += f"<li>{stripped[2:]}</li>"
            elif stripped: html_out += f"<p>{stripped}</p>"
            
    # 处理末尾残留表格
    if inside_table and table_buffer:
        b64 = create_table_img_b64(table_buffer)
        if b64:
             html_out += f'<br><img src="data:image/png;base64,{b64}" style="max-width:100%; border:1px solid #ddd;" /><br>'
    
    html_out += "</div>"
    return html_out

def generate_word_doc(html_content):
    """为了 Word 下载功能简单生成一个 docx"""
    doc = Document()
    doc.add_paragraph("Please use the 'Copy' button on the left to copy rich text with images.")
    # 这里只是占位，因为用户主要需求是复制
    bio = io.BytesIO()
    doc.save(bio)
    return bio

# --- UI ---

with st.sidebar:
    api_key = st.text_input("API Key", value="sk-3UIO8MwTblfyQuEZz2WUCzQOuK4QwwIPALVcNxFFNUxJayu7", type="password")
    model_name = st.selectbox("Model", ["gemini-3-pro", "gpt-4o"])

st.title("💎 Pro Research (JS Copy Engine)")

uploaded_file = st.file_uploader("上传 PDF", type=['pdf'])

if uploaded_file and st.button("🚀 生成"):
    api_url = "https://api.nuwaapi.com/v1/chat/completions"
    
    with st.spinner("1. 读取 PDF..."):
        raw_text = extract_text(uploaded_file)
        
    chunks = [raw_text[i:i+4000] for i in range(0, len(raw_text), 4000)]
    full_md = []
    
    progress = st.progress(0)
    for i, chunk in enumerate(chunks):
        with st.spinner(f"2. 数字化 Part {i+1}/{len(chunks)}..."):
            # 强制 AI 输出 Markdown 表格
            prompt = "OCR Task. Output EXACT text. Detect TABLES and format as Markdown (| col |...)."
            msg = [{"role": "user", "content": f"{prompt}\n\n{chunk}"}]
            res = call_ai(api_key, model_name, msg)
            full_md.append(res if res else chunk)
        progress.progress((i+1)/len(chunks))
        
    full_text = "\n\n".join(full_md)
    
    with st.spinner("3. 渲染图片与 HTML..."):
        # 核心：生成包含 Base64 图片的 HTML 字符串
        final_html = process_content_to_html(full_text)
        
    with st.spinner("4. 撰写社媒..."):
        msg_s = [{"role": "user", "content": f"Write social media posts based on:\n{full_text[:5000]}"}]
        social = call_ai(api_key, model_name, msg_s)

    st.session_state['current_report'] = {
        "html": final_html,
        "social": social,
        "filename": uploaded_file.name
    }
    st.rerun()

# --- 结果展示 ---
curr = st.session_state['current_report']
if curr:
    st.divider()
    col1, col2 = st.columns([6, 4])
    
    with col1:
        st.subheader("📋 原始内容 (图文版)")
        
        # --- 核心：JS 一键复制组件 ---
        # 我们注入一段 HTML+JS。
        # 1. 隐藏的 div 存放内容。
        # 2. 一个漂亮的按钮。
        # 3. 脚本：点击按钮 -> 提取隐藏 div 的 html -> 写入 clipboard
        
        components.html(f"""
        <html>
        <head>
            <style>
                .copy-btn {{
                    background-color: #4CAF50; border: none; color: white; 
                    padding: 15px 32px; text-align: center; text-decoration: none;
                    display: inline-block; font-size: 16px; margin: 4px 2px; 
                    cursor: pointer; border-radius: 8px; font-weight: bold;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }}
                .copy-btn:active {{ background-color: #3e8e41; transform: translateY(2px); }}
                .status {{ margin-left: 10px; color: #666; font-family: sans-serif; }}
            </style>
        </head>
        <body>
            <!-- 按钮 -->
            <button class="copy-btn" onclick="copyToClipboard()">📋 点击一键复制到 Word/微信</button>
            <span id="status" class="status"></span>

            <!-- 这里是真正的内容，包含Base64图片 -->
            <div id="content" style="border:1px solid #eee; padding:20px; margin-top:10px; border-radius:5px; background:white;">
                {curr['html']}
            </div>

            <script>
                async function copyToClipboard() {{
                    const node = document.getElementById('content');
                    const status = document.getElementById('status');
                    
                    try {{
                        // 创建 Blob 对象，类型为 text/html
                        // 包含 Base64 图片的 HTML 需要作为 rich text 写入
                        const htmlContent = node.innerHTML;
                        const blobHtml = new Blob([htmlContent], {{ type: 'text/html' }});
                        const blobText = new Blob([node.innerText], {{ type: 'text/plain' }});
                        
                        const data = [new ClipboardItem({{ 
                            'text/html': blobHtml,
                            'text/plain': blobText 
                        }})];
                        
                        await navigator.clipboard.write(data);
                        
                        status.innerText = "✅ 已复制！请直接去 Word 粘贴 (Ctrl+V)";
                        status.style.color = "green";
                    }} catch (err) {{
                        console.error('Failed to copy: ', err);
                        status.innerText = "❌ 复制失败 (浏览器限制)。请手动全选下方内容复制。";
                        status.style.color = "red";
                    }}
                }}
            </script>
        </body>
        </html>
        """, height=800, scrolling=True)

    with col2:
        st.subheader("🔥 社媒文案")
        st.text_area("Social", value=curr['social'], height=800)

elif not uploaded_file:
    st.info("请上传 PDF。本版本内置 JavaScript 剪贴板引擎，生成结果后点击绿色按钮即可完美复制图片和文字。")
