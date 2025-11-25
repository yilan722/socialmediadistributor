import streamlit as st
import streamlit.components.v1 as components
import requests
import pdfplumber
import io
import re
import textwrap
import pandas as pd
import matplotlib.pyplot as plt
import base64
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

# --- 全局配置 ---
st.set_page_config(page_title="Pro Research (Final Integrity)", layout="wide", page_icon="💎")

# 绘图配置 (解决中文乱码)
plt.style.use('ggplot')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial', 'Microsoft YaHei'] 
plt.rcParams['axes.unicode_minus'] = False

# --- 核心工具函数 ---

def extract_text(uploaded_file):
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t: text += f"\n{t}"
    return text

def call_ai(api_key, model, messages, temperature=0.1):
    url = "https://api.nuwaapi.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": temperature}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=120)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content']
        return None
    except: return None

def generate_table_image_base64(table_lines):
    """
    暴力绘图引擎：只要给list，就算只有一行也画成图片
    """
    try:
        # 1. 清洗和解析
        data = []
        for line in table_lines:
            # 去除 markdown 分割线 |---|
            if set(line.strip().replace('|','').replace('-','').replace(':','').replace(' ','')) == set():
                continue
            # 按竖线分割
            cells = [c.strip() for c in line.split('|') if c.strip() != '']
            if cells:
                data.append(cells)
        
        if not data: return None

        # 补齐列数
        max_cols = max(len(row) for row in data)
        final_data = [row + [""]*(max_cols-len(row)) for row in data]
        
        if not final_data: return None

        headers = final_data[0]
        body = final_data[1:]
        if not body: body = [[""]*len(headers)] 

        # 2. 绘图
        df = pd.DataFrame(body, columns=headers)
        
        # 动态计算高度
        row_heights = []
        col_width = 22
        for row in body:
            max_lines = 1
            for item in row:
                lines_count = len(textwrap.wrap(str(item), width=col_width))
                if lines_count > max_lines: max_lines = lines_count
            row_heights.append(max_lines)

        base_h = 0.5
        total_h = 0.8 + sum([rh * base_h for rh in row_heights])
        total_w = min(len(headers) * 3, 14)

        fig, ax = plt.subplots(figsize=(total_w, total_h))
        ax.axis('off')
        
        table = ax.table(cellText=df.values, colLabels=df.columns, loc='center', cellLoc='left')
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        
        # 样式
        cells = table.get_celld()
        for (row, col), cell in cells.items():
            cell.set_linewidth(1)
            cell.set_edgecolor('#cccccc')
            cell.set_text_props(position=(0.02, cell.get_text_props()['position'][1]))
            
            if row == 0:
                cell.set_facecolor('#2c3e50')
                cell.set_text_props(color='white', weight='bold', ha='center')
                cell.set_height(0.8/total_h)
            else:
                rh = row_heights[row-1]
                cell.set_facecolor('#f9f9f9' if row%2 else 'white')
                cell.set_text_props(color='black', wrap=True)
                cell.set_height((rh*base_h)/total_h)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=150, pad_inches=0.1)
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"Img Error: {e}")
        return None

def process_text_to_html(full_text):
    """
    将文本转为 HTML，同时扫描表格并替换为 Base64 图片
    """
    lines = full_text.split('\n')
    html_parts = []
    
    table_buffer = []
    inside_table = False
    
    for line in lines:
        stripped = line.strip()
        # 【核心判定】只要这一行包含竖线 | 且字符数大于3，就视为表格行
        is_table_row = '|' in stripped and len(stripped) > 3
        
        if is_table_row:
            if not inside_table:
                inside_table = True
            table_buffer.append(stripped)
        else:
            if inside_table:
                # 表格结束，立即生成图片
                b64 = generate_table_image_base64(table_buffer)
                if b64:
                    # 嵌入图片
                    html_parts.append(f'<div class="table-img"><img src="data:image/png;base64,{b64}"></div>')
                else:
                    # 失败回退
                    html_parts.append(f"<pre>{chr(10).join(table_buffer)}</pre>")
                
                inside_table = False
                table_buffer = []
            
            # 处理普通文本
            if not stripped: continue
            
            if stripped.startswith('### '): html_parts.append(f"<h3>{stripped[4:]}</h3>")
            elif stripped.startswith('## '): html_parts.append(f"<h2>{stripped[3:]}</h2>")
            elif stripped.startswith('# '): html_parts.append(f"<h1>{stripped[2:]}</h1>")
            elif stripped.startswith('- ') or stripped.startswith('* '): html_parts.append(f"<li>{stripped[2:]}</li>")
            else: html_parts.append(f"<p>{stripped}</p>")

    # 处理末尾
    if inside_table and table_buffer:
        b64 = generate_table_image_base64(table_buffer)
        if b64:
            html_parts.append(f'<div class="table-img"><img src="data:image/png;base64,{b64}"></div>')
        else:
            html_parts.append(f"<pre>{chr(10).join(table_buffer)}</pre>")
            
    return "\n".join(html_parts)

# --- UI 界面 ---
with st.sidebar:
    api_key = st.text_input("API Key", value="sk-3UIO8MwTblfyQuEZz2WUCzQOuK4QwwIPALVcNxFFNUxJayu7", type="password")
    model_name = st.selectbox("Model", ["gemini-3-pro", "gpt-4o"])

st.title("💎 Pro Research (Visual Copy + Social Media)")

uploaded_file = st.file_uploader("上传 PDF", type=['pdf'])

if uploaded_file and st.button("🚀 开始转换"):
    api_url = "https://api.nuwaapi.com/v1/chat/completions"
    
    # 1. 提取
    with st.spinner("1. 读取 PDF..."):
        raw_text = extract_text(uploaded_file)
        
    # 2. 格式化 (强制 Markdown 表格)
    chunks = [raw_text[i:i+4000] for i in range(0, len(raw_text), 4000)]
    full_md_list = []
    
    progress = st.progress(0)
    for i, chunk in enumerate(chunks):
        with st.spinner(f"2. 数字化 (Part {i+1}/{len(chunks)})..."):
            prompt = """
            You are an advanced OCR engine.
            Task: Transcribe the text exactly (1:1).
            
            CRITICAL RULES:
            1. **TABLES**: You MUST output tables using Markdown format (| Col1 | Col2 |).
            2. **TEXT**: Keep all text exactly as it appears. Do not summarize.
            """
            msg = [{"role": "user", "content": f"{prompt}\n\nCONTENT:\n{chunk}"}]
            res = call_ai(api_key, model_name, msg)
            full_md_list.append(res if res else chunk)
        progress.progress((i+1)/len(chunks))
        
    full_md_text = "\n".join(full_md_list)
    
    # 3. 生成社媒 (核心功能回归！)
    with st.spinner("3. 正在撰写社媒文案 (Lead Analyst)..."):
        social_prompt = """
        Act as a Lead Analyst at a Hedge Fund.
        Write social media content (LinkedIn, Twitter Thread, Reddit) based on the report.
        Focus on:
        - Key Investment Logic
        - Numerical Catalysts
        - Upside Potential
        Separate platforms with '==='.
        """
        # 截取前 6000 字作为上下文
        msg_social = [{"role": "user", "content": f"{social_prompt}\n\nREPORT:\n{full_md_text[:6000]}"}]
        social_res = call_ai(api_key, model_name, msg_social, temperature=0.7)

    # 4. 生成可视化 HTML
    with st.spinner("4. 渲染表格图片..."):
        final_html = process_text_to_html(full_md_text)

    # 存入 Session
    st.session_state['report'] = {
        "html": final_html,
        "social": social_res,
        "filename": uploaded_file.name
    }
    st.rerun()

# --- 结果展示 ---
if 'report' in st.session_state:
    curr = st.session_state['report']
    
    st.divider()
    col1, col2 = st.columns([6, 4])
    
    # === 左侧：图文并茂的复制区 ===
    with col1:
        st.subheader("📄 1:1 原始内容 (含表格图片)")
        st.info("👇 点击下方绿色按钮，即可一键复制所有内容（图片+文字）到 Word/微信。")
        
        # 嵌入 HTML + JS 复制脚本
        components.html(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 10px; }}
                .btn {{
                    background: #28a745; color: white; border: none; padding: 12px 24px;
                    font-size: 16px; font-weight: bold; border-radius: 6px; cursor: pointer;
                    width: 100%; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);
                }}
                .btn:active {{ transform: scale(0.98); }}
                #content-area {{
                    border: 1px solid #ddd; padding: 30px; background: white;
                    box-shadow: 0 0 10px rgba(0,0,0,0.05); border-radius: 4px;
                }}
                img {{ max-width: 100%; border: 1px solid #eee; margin: 10px 0; }}
                h1, h2, h3 {{ color: #333; }}
                li {{ margin-left: 20px; }}
            </style>
        </head>
        <body>
            <button class="btn" onclick="copyContent()">📋 一键复制 (含图片)</button>
            <div id="msg" style="text-align:center; margin-bottom:10px; height:20px;"></div>
            
            <div id="content-area">
                {curr['html']}
            </div>

            <script>
                async function copyContent() {{
                    const node = document.getElementById('content-area');
                    const msg = document.getElementById('msg');
                    try {{
                        const htmlBlob = new Blob([node.innerHTML], {{type: 'text/html'}});
                        const textBlob = new Blob([node.innerText], {{type: 'text/plain'}});
                        const item = new ClipboardItem({{ 'text/html': htmlBlob, 'text/plain': textBlob }});
                        await navigator.clipboard.write([item]);
                        
                        msg.innerHTML = '<span style="color:green; font-weight:bold;">✅ 复制成功！请去粘贴。</span>';
                    }} catch (err) {{
                        console.error(err);
                        msg.innerHTML = '<span style="color:red;">❌ 浏览器阻止了复制，请手动全选下方内容。</span>';
                    }}
                }}
            </script>
        </body>
        </html>
        """, height=1000, scrolling=True)

    # === 右侧：社媒文案 (绝不丢失) ===
    with col2:
        st.subheader("🔥 深度社媒文案 (Lead Analyst)")
        st.text_area("Social Media Content", value=curr['social'], height=1000)

elif not uploaded_file:
    st.info("请上传 PDF。本版本已恢复社媒功能，并强制将表格转换为图片以便复制。")
