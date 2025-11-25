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
from docx.shared import Inches

# --- 全局配置 ---
st.set_page_config(page_title="Pro Research (Image Table Fixed)", layout="wide", page_icon="💎")

# 绘图配置
plt.style.use('ggplot')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial', 'Microsoft YaHei'] 
plt.rcParams['axes.unicode_minus'] = False

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
    payload = {"model": model, "messages": messages, "temperature": 0.1}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=120)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content']
        return None
    except: return None

def generate_table_image_base64(table_text):
    """
    将文本内容强制绘制成表格图片，返回 Base64 字符串
    """
    try:
        # 1. 预处理：按行分割，按竖线或两空格分割
        lines = table_text.strip().split('\n')
        data = []
        
        # 尝试解析 Markdown 表格
        for line in lines:
            line = line.strip()
            if not line: continue
            # 过滤分割线 |---|
            if set(line.replace('|','').replace('-','').replace(' ','')) == set():
                continue
            
            # 拆分单元格
            if '|' in line:
                cells = [c.strip() for c in line.split('|') if c.strip() != '']
            else:
                # 如果没有竖线，尝试用多个空格拆分
                cells = [c.strip() for c in re.split(r'\s{2,}', line) if c.strip()]
            
            if cells:
                data.append(cells)

        if not data: return None

        # 补齐列数
        max_cols = max(len(row) for row in data)
        final_data = [row + [""]*(max_cols-len(row)) for row in data]
        
        # 分离表头
        headers = final_data[0]
        body = final_data[1:]
        if not body: body = [[""]*len(headers)] # 防止只有表头

        # 2. 绘图
        df = pd.DataFrame(body, columns=headers)
        
        # 计算动态行高
        row_heights = []
        col_width = 20
        for row in body:
            max_lines = 1
            for item in row:
                # 估算换行
                lines_count = len(textwrap.wrap(str(item), width=col_width))
                if lines_count > max_lines: max_lines = lines_count
            row_heights.append(max_lines)

        # 图片尺寸
        base_h = 0.5
        total_h = 1.0 + sum([rh * base_h for rh in row_heights])
        total_w = min(len(headers) * 3, 14)

        fig, ax = plt.subplots(figsize=(total_w, total_h))
        ax.axis('off')
        
        # 绘制
        table = ax.table(cellText=df.values, colLabels=df.columns, loc='center', cellLoc='left')
        table.auto_set_font_size(False)
        table.set_fontsize(12)
        
        # 美化
        cells = table.get_celld()
        for (row, col), cell in cells.items():
            cell.set_linewidth(1)
            cell.set_edgecolor('#a0a0a0')
            cell.set_text_props(position=(0.02, cell.get_text_props()['position'][1])) # padding
            
            if row == 0:
                cell.set_facecolor('#404040')
                cell.set_text_props(color='white', weight='bold', ha='center')
                cell.set_height(0.8/total_h)
            else:
                cell.set_facecolor('#f5f5f5' if row % 2 else 'white')
                cell.set_text_props(color='black', wrap=True)
                rh = row_heights[row-1]
                cell.set_height((rh * base_h)/total_h)

        # 保存
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=150, pad_inches=0.1)
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.getvalue()).decode()

    except Exception as e:
        print(f"Table Gen Error: {e}")
        return None

def process_text_to_html_blocks(full_text):
    """
    核心解析逻辑：
    1. 找到 [[TABLE_START]] ... [[TABLE_END]]
    2. 将中间内容转图片
    3. 其他内容保留格式
    """
    # 正则分割：保留分隔符以便知道哪里是表格
    # pattern 匹配 [[TABLE_START]] (内容) [[TABLE_END]]
    pattern = re.compile(r'(\[\[TABLE_START\]\][\s\S]*?\[\[TABLE_END\]\])')
    
    parts = pattern.split(full_text)
    
    html_out = """<div id="copy-content" style="font-family: 'Arial', sans-serif; line-height: 1.6; color: #333;">"""
    
    for part in parts:
        if "[[TABLE_START]]" in part:
            # === 这是一个表格区域 ===
            # 提取纯文本内容
            raw_table = part.replace("[[TABLE_START]]", "").replace("[[TABLE_END]]", "").strip()
            
            # 生成图片 Base64
            img_b64 = generate_table_image_base64(raw_table)
            
            if img_b64:
                # 插入图片
                html_out += f"""
                <div style="margin: 20px 0; text-align: center;">
                    <img src="data:image/png;base64,{img_b64}" style="max-width: 100%; border: 1px solid #ccc; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);">
                </div>
                """
            else:
                # 失败回退
                html_out += f"<pre style='background:#f4f4f4; padding:10px;'>{raw_table}</pre>"
        
        else:
            # === 这是普通文本区域 ===
            # 简单格式化
            lines = part.split('\n')
            for line in lines:
                s = line.strip()
                if not s: continue
                
                if s.startswith('### '): html_out += f"<h3 style='margin-top:15px; color:#444;'>{s[4:]}</h3>"
                elif s.startswith('## '): html_out += f"<h2 style='border-bottom:2px solid #eee; padding-bottom:5px;'>{s[3:]}</h2>"
                elif s.startswith('# '): html_out += f"<h1 style='color:#222;'>{s[2:]}</h1>"
                elif s.startswith('- ') or s.startswith('* '): html_out += f"<li style='margin-left:20px;'>{s[2:]}</li>"
                else: html_out += f"<p style='margin-bottom:10px;'>{s}</p>"
                
    html_out += "</div>"
    return html_out

# --- UI ---
with st.sidebar:
    api_key = st.text_input("API Key", value="sk-3UIO8MwTblfyQuEZz2WUCzQOuK4QwwIPALVcNxFFNUxJayu7", type="password")
    model_name = st.selectbox("Model", ["gemini-3-pro", "gpt-4o"])

st.title("💎 Pro Research: 1:1 PDF Converter")
st.markdown("Feature: **PDF Tables -> Real Images** | **Text -> Editable Text**")

uploaded_file = st.file_uploader("Upload PDF", type=['pdf'])

if uploaded_file and st.button("🚀 Start Conversion"):
    api_url = "https://api.nuwaapi.com/v1/chat/completions"
    
    with st.spinner("1. Reading PDF..."):
        raw_text = extract_text(uploaded_file)
        
    chunks = [raw_text[i:i+4000] for i in range(0, len(raw_text), 4000)]
    full_res = []
    
    progress = st.progress(0)
    for i, chunk in enumerate(chunks):
        with st.spinner(f"2. Processing Part {i+1}/{len(chunks)}..."):
            # === 核心 Prompt：强制标签 ===
            prompt = """
            You are a format conversion engine.
            Task: Convert PDF text to Markdown.
            
            CRITICAL RULES FOR TABLES:
            1. Whenever you encounter a table (data with rows and columns), you MUST wrap it in tags:
               [[TABLE_START]]
               ... table content (keep logic, can be | separated or just aligned) ...
               [[TABLE_END]]
               
            2. For all other text: Output exactly as is (1:1 copy).
            3. Do not summarize.
            """
            msg = [{"role": "user", "content": f"{prompt}\n\nCONTENT:\n{chunk}"}]
            res = call_ai(api_key, model_name, msg)
            full_res.append(res if res else chunk)
        progress.progress((i+1)/len(chunks))
        
    full_converted_text = "\n".join(full_res)
    
    with st.spinner("3. Rendering Images & Generating Copy-Ready View..."):
        # 生成带图片的 HTML
        final_html = process_text_to_html_blocks(full_converted_text)

    # 存入 Session
    st.session_state['result'] = final_html
    st.rerun()

# --- 结果展示 ---
if 'result' in st.session_state:
    st.divider()
    
    # CSS 样式：定义复制按钮和显示区域
    st.markdown("""
    <style>
    .copy-container {
        position: relative;
    }
    .main-btn {
        background-color: #00C853; 
        color: white; 
        padding: 12px 24px; 
        border: none; 
        border-radius: 5px; 
        font-size: 16px; 
        cursor: pointer; 
        width: 100%;
        margin-bottom: 10px;
        font-weight: bold;
    }
    .main-btn:hover { background-color: #00E676; }
    </style>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 8])
    
    with col1:
        st.info("👈 点击右侧绿色按钮，即可将【包含图片表格】的完整内容复制到剪贴板。")
        st.warning("如果图片未显示，请检查 API 模型是否正确识别了表格。")

    with col2:
        # === 核心 JS 组件：一键复制 ===
        html_content = st.session_state['result']
        
        # 这里的 HTML 包含了 Base64 图片
        # 我们用 JS 将其写入 Clipboard
        components.html(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
        </head>
        <body style="margin:0; padding:0; font-family: sans-serif;">
            
            <button onclick="doCopy()" style="
                background-color: #00C853; color: white; border: none; padding: 15px; 
                width: 100%; font-size: 18px; font-weight: bold; border-radius: 8px; 
                cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                📋 点击这里：一键复制所有内容 (含图片)
            </button>
            
            <div id="status" style="margin-top:10px; text-align:center; color:#555;"></div>

            <!-- 可视化区域 -->
            <div id="doc-content" style="
                border: 1px solid #e0e0e0; 
                padding: 40px; 
                margin-top: 20px; 
                background: white; 
                box-shadow: 0 0 15px rgba(0,0,0,0.05);
                border-radius: 4px;">
                {html_content}
            </div>

            <script>
                async function doCopy() {{
                    const node = document.getElementById('doc-content');
                    const status = document.getElementById('status');
                    
                    try {{
                        // 构建 ClipboardItem
                        // 必须同时提供 text/html 和 text/plain
                        const htmlBlob = new Blob([node.innerHTML], {{type: 'text/html'}});
                        const textBlob = new Blob([node.innerText], {{type: 'text/plain'}});
                        
                        const item = new ClipboardItem({{
                            'text/html': htmlBlob,
                            'text/plain': textBlob
                        }});
                        
                        await navigator.clipboard.write([item]);
                        
                        status.innerHTML = "✅ <b>复制成功！</b> 现在去 Word 或 微信 粘贴 (Ctrl+V) 即可看到图片。";
                        status.style.color = "green";
                        
                    }} catch (err) {{
                        console.error(err);
                        status.innerText = "❌ 自动复制失败 (浏览器限制)。请手动选中下方内容复制。";
                        status.style.color = "red";
                    }}
                }}
            </script>
        </body>
        </html>
        """, height=1000, scrolling=True)

elif not uploaded_file:
    st.info("Waiting for PDF upload...")
