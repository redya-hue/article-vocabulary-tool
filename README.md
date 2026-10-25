# 文章词汇提取 · API 修正版 2.0

输入英文文章，提取较高难度单词和专业短语，导出六列 CSV：
`word,phonetic,meaning,example,translation,pos`。已移除 source 输入框与导出列。

## 为什么旧版只留下 20 条

程序没有 20 条数量限制。旧版每批可输入约 4500 字符，输出上限为 7000 token，而且每条词汇都要求模型重复输出整句英文与中文翻译。某一批触及输出限制后，程序停止后续处理，只保留此前成功批次的结果；20 条是当时已完成的数量。

新版每批约 1500 字符，由程序回填英文原句，同一句中文翻译只请求一次。默认输出上限 8000 token，可在界面修改。DeepSeek 官方接口使用非思考模式和 JSON 输出。若仍遇到截断或不完整 JSON，自动拆小该批继续；拆分有边界，不会无限重试。网络、鉴权或余额等错误会暂停，不盲目重试。自动拆分会增加 API 请求，可能增加费用。

## Windows 使用方法

1. 安装 Python 3.10 或更新版本，勾选 Add Python to PATH。
2. 关闭旧程序，将此包完整解压到新文件夹，双击 start_windows.bat。
3. 粘贴文章，或导入 TXT、MD、DOCX、PDF；PDF 解析库已随包附带，无需另外安装。扫描版 PDF 需自行 OCR。
4. 输入研究领域，保留“专业单词与短语”选项，可识别 carbon sequestration、soil respiration 等原文连续短语。
5. 填写 API 地址、模型和 Key。默认示例为 https://api.deepseek.com 与 deepseek-flash；其他服务需填写其兼容 Chat Completions 的地址及模型。地址可为根地址或完整 /chat/completions 地址，若服务要求 /v1，请自行填写。
6. 点击“自动提取 / 继续”，查看处理状态和结果。双击词条查看原句、译文及筛选依据；可多选删除不需要的词。
7. 点击“导出 CSV + 核验记录”。CSV 使用 UTF-8 BOM 编码，可在 Windows Excel 中打开。

命令行运行：`python article_vocab.py`。可用 VOCAB_API_BASE、VOCAB_MODEL、VOCAB_API_KEY 环境变量预填配置。
程序不会保存 API Key。正文会发到你填写的服务商，API 调用可能收费；本程序不收取订阅费。

## 断点继续与完成状态

每个成功的小批次自动保存到本机。保持文章、API 地址、模型、领域和提取设置一致，再点“自动提取 / 继续”即可复用成功部分；修改输出上限仍可复用。已拆分的失败父批次不会重复请求。

Windows 进度位置为 `%LOCALAPPDATA%/ArticleVocabularyAPI/checkpoints/`；其他系统通常是 `~/.cache/ArticleVocabularyAPI/checkpoints/`。进度包含提取结果和失败片段，不包含 Key。请按自己的需要保留或删除。

取消“复用本地进度”会重新提取，产生新的调用费用。预览中手动删除词条不会改写批次缓存，继续处理时可能恢复被删除的词。旧版没有保存断点，旧版已经得到的 20 条不能自动作为新版进度；建议先保留旧版导出文件。

只有所有批次成功才显示全文处理完成。失败或主动停止时会明确显示部分完成，已成功结果可导出；仍失败的片段保存在核验记录中。点击停止会等待当前网络请求结束，超时最长约 150 秒。
“全文处理完成”表示批次均处理成功，不保证模型没有漏词。程序没有固定词数上限，也不会为了超过 20 条而加入简单词。

默认可跳过独立 References / Bibliography 标题之后的内容；若该标题不是文章末尾的参考文献，请取消此选项。很长的句子会拆为原文片段，此时 example 是该片段。PDF 分栏、断行、连字符和页眉页脚可能影响正文质量，导入后应检查。

## 筛选规则

普通单词采用偏严格的操作定义：
`（六级词表 ∪ 托福词表 ∪ SAT 词表）−（初中词表 ∪ 高中词表 ∪ 四级词表 ∪ 基础停用词）`。
这是公开词表匹配规则，不是官方难度认证，可能漏掉值得学习的词。he、she、a、the 等会被本地过滤。专业单词由模型判断，但基础词排除优先；专业短语按整体概念判断，可包含基础词，需在原文连续出现，支持 2—6 词。

模型返回的词形、原文位置会被核验；复杂词形还原可能遗漏。释义、音标、词性、译文及专业性仍需复核，程序不能保证它们永远正确。

## 导出与手动模式

| 列 | 含义 |
| --- | --- |
| word | 单词原形或原文专业短语 |
| phonetic | 音标，不确定或专业短语留空 |
| meaning | 语境下的中文释义 |
| example | 本地回填的原文句子或片段 |
| translation | 原句或片段的中文翻译 |
| pos | 词性，例如 n.、v.、adj.、n. phr. |

同名 .audit.json 保存核验依据、过滤原因、批次状态、API 调用统计及失败片段。同名文件会被替换。按 word + pos 去重，保留首次例句。尚未对 WordMemorizer 的实际导入流程做端到端验证。

“无 API：复制提示词”模式仍保留：复制提示词到你使用的 AI 对话，取得完整 JSON，再粘贴回本工具。每次最多 50000 字符；修改正文后应重新复制提示词。新 JSON 使用 items 数组与 translations 译文映射，也兼容旧版每条包含 example/translation 的结构。

可离线检验：导入 example_article.txt，先复制提示词，再粘贴 example_response.json。预期保留 3 条、过滤 he。示例是人工编写的测试数据。

## 检验与许可

运行 `python -m unittest discover -s tests -v`。28 项自动测试覆盖词表过滤、短语核验、CSV、超过 20 条、模拟 API 截断拆分、失败恢复与断点复用。未调用你的付费 API，未在 Windows 上实测 GUI 或外部模型。

词表来源：https://github.com/KyleBing/english-vocabulary ，获取日期 2026-10-25。原始词表采用 BSD-3-Clause，许可见 data/LICENSE.txt，来源与校验和见 data/SOURCES.json。随包 pypdf 的许可保留于 vendor/pypdf-6.21.2.dist-info/licenses/LICENSE。本工具代码采用 MIT，见 LICENSE.txt。

DeepSeek 参数文档：https://api-docs.deepseek.com/api/create-chat-completion/
