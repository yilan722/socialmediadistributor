# 📱 Social Media Distributor Agent

一个强大的投资研报转化工具，将 PDF 投资报告自动转化为专业的 LinkedIn 长文和全平台社交媒体文案。

## ✨ 功能特性

- 📄 **PDF 全文解析**：完整提取 PDF 中的所有内容，支持多页文档
- 📊 **智能内容转化**：将原始报告转化为专业的 LinkedIn 文章
- 📱 **全平台社媒文案**：自动生成 LinkedIn、Twitter、小红书、Reddit 等多平台文案
- 📝 **Word 文档导出**：生成格式化的 Word 文档，支持表格和图表
- 🤖 **多模型支持**：支持 Gemini、Qwen、GPT、Claude 等多种 AI 模型
- 💾 **历史记录**：保存处理历史，方便后续查看和下载

## 🚀 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行应用

```bash
streamlit run app.py
```

## ⚙️ 配置

### API Key 设置

在侧边栏输入你的 API Key，或修改代码中的默认值。

### 模型选择

支持以下模型：
- `gemini-3-pro` - 推荐用于长文档处理
- `gemini-2.5-pro` - 支持超长上下文
- `qwen-max` - 中文语境表现优异
- `gpt-4o` - OpenAI 最新模型

## 📋 使用流程

1. 上传 PDF 投资报告
2. 选择 AI 模型
3. 点击"开始生成文案 & 报告"
4. 等待处理完成
5. 下载 Word 文档或复制社媒文案

## 🛠️ 技术栈

- **Streamlit** - Web 应用框架
- **pdfplumber** - PDF 文本提取
- **python-docx** - Word 文档生成
- **matplotlib** - 表格可视化
- **pandas** - 数据处理

## 📝 注意事项

- 确保上传的 PDF 是可提取文字的版本（非纯图片扫描件）
- 长文档建议使用 Gemini 系列模型以获得最佳效果
- API Key 请妥善保管，建议使用环境变量或 Streamlit Secrets

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

