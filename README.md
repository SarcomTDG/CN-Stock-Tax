# 境外投资税务试算工具（CN Tax Estimator）

基于长桥证券 OpenAPI 的 Flask 应用，一键拉取资金流水，按「交易所得」「股息利息」「境外已扣税」三大维度自动拆分，并依据中国大陆 20 % 税率估算应补税额，支持分市场（美股 / 港股 / A 股 / 新加坡 / 其他）独立统计与 Excel 导出。（futu还在编写中）

---

## 功能速览
| 功能 | 说明 |
|---|---|
| 🔍 自动分类 | 智能识别 BUY / SELL / DIVIDEND / TAX 等 10+ 种流水类型 |
| 🧮 税务试算 | 交易差价 & 股息利息分开计税，亏损自动清零，境外已缴税可抵免 |
| 🌏 多市场 | 支持 US / HK / CN / SG / OTHER 五市场独立核算 |
| 📊 可视化 | Element-UI 表格 + 卡片，金额红绿配色，一眼看懂盈亏 |
| 📥 一键导出 | 前端直接生成多 Sheet Excel，含汇总 + 明细 |

---

## 目录结构

```text
project/
├── app.py              # Flask 后端核心逻辑，包含路由分发与 API 接口
├── requirements.txt    # Python 环境依赖列表
├── templates/
│   └── index.html      # 前端单页面 (包含 Vue2 框架、Element-UI 组件库与业务逻辑)
└── README.md           # 项目使用说明文档
```


---

## 1. 快速开始

### 1.1 克隆 & 安装
python 3.10+
```bash
git clone https://github.com/SarcomTDG/CN-Stock-Tax
cd cn-tax-estimator
pip install -r requirements.txt
```
### 1.2 配置长桥 API
编辑 app.py 顶部 LB_CONFIG，填入你的长桥凭证：

```bash
LB_CONFIG = {
    "app_key": "你的AppKey",
    "app_secret": "你的AppSecret",
    "access_token": "你的AccessToken"
}
```
如未开通，请前往 长桥开放平台 申请。

### 1.3 启动服务
```bash
python app.py
# 默认端口 5000
# 浏览器访问 http://localhost:5000
```